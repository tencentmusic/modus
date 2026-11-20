//! Read-only discovery of published Modus knowledge. Machine caches, sessions,
//! plans and skills installed for a host agent are deliberately not knowledge.
use crate::core::error::AppError;
use serde::Serialize;
use std::path::{Path, PathBuf};
use walkdir::WalkDir;

const MAX_ENTRIES: usize = 100_000;
const MAX_DOCUMENT_BYTES: u64 = 2 * 1024 * 1024;

#[derive(Debug, Serialize)]
pub struct KnowledgeDocument {
    pub path: String,
    pub relative_path: String,
    pub project_path: String,
    pub project_name: String,
    pub title: String,
    pub description: Option<String>,
    pub category: String,
    pub modified_at: Option<u64>,
}

#[derive(Debug, Serialize)]
pub struct KnowledgeScan {
    pub documents: Vec<KnowledgeDocument>,
    pub warnings: Vec<String>,
}

fn is_knowledge_root(path: &Path) -> bool {
    path.file_name().is_some_and(|n| n == "knowledge")
        && path
            .parent()
            .and_then(Path::file_name)
            .is_some_and(|n| n == "modus")
}

fn read_document(path: &Path) -> Result<String, AppError> {
    // Bound reads even if the file grows after metadata was checked.
    use std::io::Read;
    let file = std::fs::File::open(path)?;
    if !file.metadata()?.is_file() {
        return Err(AppError::invalid_input("Expected a Markdown file"));
    }
    let mut bytes = Vec::new();
    file.take(MAX_DOCUMENT_BYTES + 1).read_to_end(&mut bytes)?;
    if bytes.len() as u64 > MAX_DOCUMENT_BYTES {
        return Err(AppError::invalid_input("Knowledge document exceeds 2 MiB"));
    }
    String::from_utf8(bytes).map_err(|error| AppError::invalid_input(error.to_string()))
}

fn metadata(content: &str, fallback: &str) -> (String, Option<String>) {
    let mut title = None;
    let mut description = None;
    if let Some(rest) = content
        .strip_prefix("---\n")
        .or_else(|| content.strip_prefix("---\r\n"))
    {
        if let Some(end) = rest.lines().position(|line| line.trim() == "---") {
            let yaml = rest.lines().take(end).collect::<Vec<_>>().join("\n");
            if let Ok(value) = serde_yaml::from_str::<serde_yaml::Value>(&yaml) {
                title = value
                    .get("displayName")
                    .or_else(|| value.get("name"))
                    .and_then(|v| v.as_str())
                    .map(str::to_owned);
                description = value
                    .get("description")
                    .and_then(|v| v.as_str())
                    .map(str::to_owned);
            }
        }
    }
    let title = title
        .or_else(|| {
            content
                .lines()
                .find_map(|line| line.strip_prefix("# ").map(str::to_owned))
        })
        .unwrap_or_else(|| fallback.to_owned());
    (title, description)
}

fn canonical_root(root: &Path) -> Result<PathBuf, AppError> {
    // Keep the initial workspace portable across users; file paths returned by
    // the picker are already absolute. Only a leading home marker is expanded.
    let expanded = if root == Path::new("~") || root.starts_with("~/") {
        let home = dirs::home_dir()
            .ok_or_else(|| AppError::invalid_input("Home directory unavailable"))?;
        home.join(root.strip_prefix("~").unwrap())
    } else {
        root.to_path_buf()
    };
    dunce::canonicalize(expanded).map_err(AppError::io)
}

fn scan(root: &Path, include_snapshots: bool) -> Result<KnowledgeScan, AppError> {
    let root = canonical_root(root)?;
    if !root.is_dir() {
        return Err(AppError::invalid_input("Select a scan directory"));
    }
    log::info!("modus knowledge: starting scan, include_snapshots={include_snapshots}");
    let mut result = KnowledgeScan {
        documents: Vec::new(),
        warnings: Vec::new(),
    };
    // Do not follow links: a project may link a host skill back into the same
    // tree, and scanning that alias would duplicate knowledge or escape root.
    let walker = WalkDir::new(&root)
        .follow_links(false)
        .into_iter()
        .filter_entry(|e| {
            if e.depth() == 0 {
                return true;
            }
            let name = e.file_name().to_string_lossy();
            !name.starts_with('.')
                && !matches!(
                    name.as_ref(),
                    "node_modules" | "target" | "dist" | "__pycache__"
                )
                && (include_snapshots
                    || !matches!(name.as_ref(), "evaluation" | "evaluations" | "fixtures"))
        });
    for (index, entry) in walker.enumerate() {
        if index >= MAX_ENTRIES {
            result
                .warnings
                .push("Scan stopped after 100000 entries; choose a narrower directory.".into());
            break;
        }
        let entry = match entry {
            Ok(entry) => entry,
            Err(error) => {
                result.warnings.push(error.to_string());
                continue;
            }
        };
        if !entry.file_type().is_file()
            || entry
                .path()
                .extension()
                .map_or(true, |e| !e.eq_ignore_ascii_case("md"))
        {
            continue;
        }
        let Some(knowledge) = entry.path().ancestors().find(|p| is_knowledge_root(p)) else {
            continue;
        };
        let project = knowledge.parent().and_then(Path::parent).unwrap();
        let relative = entry.path().strip_prefix(knowledge).unwrap();
        let content = match read_document(entry.path()) {
            Ok(content) => content,
            Err(error) => {
                result
                    .warnings
                    .push(format!("{}: {error}", entry.path().display()));
                continue;
            }
        };
        let (title, description) = metadata(&content, &relative.to_string_lossy());
        let category = if relative.components().count() > 1 {
            relative
                .components()
                .next()
                .unwrap()
                .as_os_str()
                .to_string_lossy()
                .into_owned()
        } else {
            "overview".into()
        };
        result.documents.push(KnowledgeDocument {
            path: entry.path().to_string_lossy().into_owned(),
            relative_path: relative.to_string_lossy().replace('\\', "/"),
            project_path: project.to_string_lossy().into_owned(),
            project_name: project
                .file_name()
                .unwrap_or_default()
                .to_string_lossy()
                .into_owned(),
            title,
            description,
            category,
            modified_at: entry
                .metadata()
                .ok()
                .and_then(|m| m.modified().ok())
                .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
                .map(|d| d.as_secs()),
        });
    }
    result.documents.sort_by(|a, b| a.path.cmp(&b.path));
    log::info!(
        "modus knowledge: scan complete, documents={}, warnings={}",
        result.documents.len(),
        result.warnings.len()
    );
    Ok(result)
}

#[tauri::command]
pub async fn scan_modus_knowledge(
    root: String,
    include_snapshots: bool,
) -> Result<KnowledgeScan, AppError> {
    tauri::async_runtime::spawn_blocking(move || scan(Path::new(&root), include_snapshots)).await?
}

fn load_document(root: &Path, path: &Path) -> Result<String, AppError> {
    let root = canonical_root(root)?;
    let path = dunce::canonicalize(path)?;
    // Revalidate on every read rather than trusting a stale frontend row.
    if !path.starts_with(&root)
        || path
            .extension()
            .map_or(true, |e| !e.eq_ignore_ascii_case("md"))
        || !path.ancestors().any(is_knowledge_root)
    {
        return Err(AppError::invalid_input(
            "Document is outside the Modus knowledge tree",
        ));
    }
    log::debug!("modus knowledge: reading document");
    read_document(&path)
}

#[tauri::command]
pub async fn get_modus_knowledge_document(root: String, path: String) -> Result<String, AppError> {
    tauri::async_runtime::spawn_blocking(move || load_document(Path::new(&root), Path::new(&path)))
        .await?
}

#[cfg(test)]
mod tests {
    use super::*;
    fn write(root: &Path, path: &str, content: &str) {
        let path = root.join(path);
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(path, content).unwrap();
    }
    #[test]
    fn discovers_published_documents_and_skips_snapshots_and_machine_files() {
        let dir = tempfile::tempdir().unwrap();
        write(
            dir.path(),
            "app/modus/knowledge/domain/orders/SKILL.md",
            "---\nname: orders\ndisplayName: 订单\ndescription: 订单知识\n---\n# Orders",
        );
        write(
            dir.path(),
            "app/modus/knowledge/architecture-overview.md",
            "# Architecture",
        );
        write(dir.path(), "app/.modus/cache/internal.md", "# Internal");
        write(dir.path(), "app/modus/plans/plan.md", "# Plan");
        write(
            dir.path(),
            "evaluation/copy/modus/knowledge/domain/a.md",
            "# Copy",
        );
        write(
            dir.path(),
            "tests/fixtures/demo/modus/knowledge/example.md",
            "# Fixture",
        );
        let result = scan(dir.path(), false).unwrap();
        assert_eq!(result.documents.len(), 2);
        assert!(result.warnings.is_empty());
        let domain = result
            .documents
            .iter()
            .find(|d| d.category == "domain")
            .unwrap();
        assert_eq!(domain.title, "订单");
        assert_eq!(domain.description.as_deref(), Some("订单知识"));
        assert_eq!(domain.project_name, "app");
        assert_eq!(scan(dir.path(), true).unwrap().documents.len(), 4);
        assert_eq!(
            scan(&dir.path().join("app/modus/knowledge"), false)
                .unwrap()
                .documents
                .len(),
            2
        );
    }
    #[test]
    fn bounded_reads_and_invalid_roots_fail_explicitly() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("large.md");
        std::fs::write(&path, vec![b'x'; MAX_DOCUMENT_BYTES as usize + 1]).unwrap();
        assert!(read_document(&path).is_err());
        assert!(scan(&path, false).is_err());
        assert!(scan(&dir.path().join("missing"), false).is_err());
    }
    #[test]
    fn reads_only_markdown_inside_selected_knowledge_tree() {
        let dir = tempfile::tempdir().unwrap();
        write(dir.path(), "app/modus/knowledge/a.md", "# Published");
        write(dir.path(), "app/modus/plans/a.md", "# Plan");
        write(dir.path(), "other/modus/knowledge/a.md", "# Other");
        let root = dir.path().join("app");
        assert_eq!(
            load_document(&root, &root.join("modus/knowledge/a.md")).unwrap(),
            "# Published"
        );
        assert!(load_document(&root, &root.join("modus/plans/a.md")).is_err());
        assert!(load_document(&root, &dir.path().join("other/modus/knowledge/a.md")).is_err());
    }
    #[cfg(unix)]
    #[test]
    fn ignores_symlinked_documents_and_directories() {
        let dir = tempfile::tempdir().unwrap();
        write(dir.path(), "app/modus/knowledge/real.md", "# Real");
        let knowledge = dir.path().join("app/modus/knowledge");
        std::os::unix::fs::symlink(knowledge.join("real.md"), knowledge.join("alias.md")).unwrap();
        std::os::unix::fs::symlink(&knowledge, knowledge.join("loop")).unwrap();
        assert_eq!(scan(dir.path(), false).unwrap().documents.len(), 1);
    }
}
