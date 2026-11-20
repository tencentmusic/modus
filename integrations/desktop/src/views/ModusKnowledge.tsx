import { useEffect, useMemo, useRef, useState } from "react";
import { BookOpen, FolderOpen, RefreshCw, Search } from "lucide-react";
import { open } from "@tauri-apps/plugin-dialog";
import { useTranslation } from "react-i18next";
import { SkillMarkdown } from "../components/SkillMarkdown";
import * as api from "../lib/tauri";
import { getErrorMessage } from "../lib/error";
import { cn } from "../utils";

export function ModusKnowledge() {
  const { t } = useTranslation();
  const [root, setRoot] = useState("");
  const [scannedRoot, setScannedRoot] = useState("");
  const [includeSnapshots, setIncludeSnapshots] = useState(false);
  const [documents, setDocuments] = useState<api.KnowledgeDocument[]>([]);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [project, setProject] = useState("");
  const [category, setCategory] = useState("");
  const [selected, setSelected] = useState<api.KnowledgeDocument | null>(null);
  const [content, setContent] = useState<string | null>(null);
  const [documentError, setDocumentError] = useState("");
  const [raw, setRaw] = useState(false);
  const scanVersion = useRef(0);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.getSettings("modus_knowledge_root").then((saved) => {
      if (!cancelled) { setRoot(saved ?? ""); setReady(true); }
    }).catch((e) => {
      if (!cancelled) { setReady(true); setError(getErrorMessage(e, t("common.error"))); }
    });
    return () => { cancelled = true; };
  }, [t]);

  useEffect(() => () => { scanVersion.current += 1; }, []);

  // A late read must never replace a newer selection or a new scan's preview.
  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    api.getModusKnowledgeDocument(scannedRoot, selected.path).then((text) => {
      if (!cancelled) setContent(text);
    }).catch((e) => { if (!cancelled) setDocumentError(getErrorMessage(e, t("common.error"))); });
    return () => { cancelled = true; };
  }, [selected, scannedRoot, t]);

  const projects = useMemo(() => [...new Map(documents.map((d) => [d.project_path, d.project_name])).entries()], [documents]);
  const categories = useMemo(() => [...new Set(documents.map((d) => d.category))].sort(), [documents]);
  const filtered = useMemo(() => {
    const term = query.trim().toLocaleLowerCase();
    return documents.filter((d) => (!project || d.project_path === project) && (!category || d.category === category)
      && `${d.title}\n${d.description ?? ""}\n${d.relative_path}\n${d.project_name}`.toLocaleLowerCase().includes(term));
  }, [documents, query, project, category]);

  async function scan() {
    if (!root.trim() || busy) return;
    const version = ++scanVersion.current;
    const scanRoot = root.trim();
    setBusy(true); setError(""); setSelected(null); setContent(null); setDocumentError("");
    try {
      const result = await api.scanModusKnowledge(scanRoot, includeSnapshots);
      if (version !== scanVersion.current) return;
      setDocuments(result.documents); setWarnings(result.warnings); setScannedRoot(scanRoot);
      setProject(""); setCategory("");
      // A settings write failure should not discard a successful scan.
      try { await api.setSettings("modus_knowledge_root", scanRoot); }
      catch (e) { if (version === scanVersion.current) setError(getErrorMessage(e, t("common.error"))); }
    } catch (e) {
      if (version === scanVersion.current) { setDocuments([]); setWarnings([]); setError(getErrorMessage(e, t("common.error"))); }
    } finally { if (version === scanVersion.current) setBusy(false); }
  }

  async function browse() {
    try {
      const path = await open({ directory: true, multiple: false });
      if (typeof path === "string") setRoot(path);
    } catch (e) { setError(getErrorMessage(e, t("common.error"))); }
  }

  function select(document: api.KnowledgeDocument) {
    setSelected(document); setContent(null); setDocumentError(""); setRaw(false);
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-5 p-6">
      <div>
        <h1 className="flex items-center gap-2 text-[17px] font-semibold text-primary"><BookOpen size={20} />{t("knowledge.title")}</h1>
        <p className="mt-1 text-[13px] text-muted">{t("knowledge.description")}</p>
      </div>
      <div className="space-y-3 rounded-xl border border-border-subtle bg-surface p-4">
        <div className="flex gap-2">
          <input aria-label={t("knowledge.root")} value={root} onChange={(e) => setRoot(e.target.value)} disabled={busy || !ready}
            className="min-w-0 flex-1 rounded-lg border border-border-subtle bg-surface px-3 py-2 text-[13px] text-primary" />
          <button onClick={browse} disabled={busy || !ready} aria-label={t("knowledge.browse")} className="rounded-lg border border-border-subtle px-3 text-secondary disabled:opacity-50"><FolderOpen size={16} /></button>
          <button onClick={scan} disabled={busy || !ready || !root.trim()} className="flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-[13px] text-white disabled:opacity-50"><RefreshCw size={15} className={busy ? "animate-spin" : ""} />{t(busy ? "knowledge.scanning" : "knowledge.scan")}</button>
        </div>
        <label className="flex items-center gap-2 text-[12px] text-secondary"><input type="checkbox" checked={includeSnapshots} disabled={busy} onChange={(e) => setIncludeSnapshots(e.target.checked)} />{t("knowledge.snapshots")}</label>
      </div>
      {error && <p role="alert" className="text-[13px] text-danger">{error}</p>}
      {warnings.length > 0 && <details className="text-[12px] text-muted"><summary>{t("knowledge.warnings", { count: warnings.length })}</summary><ul className="max-h-28 overflow-auto">{warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul></details>}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex min-w-48 flex-1 items-center gap-2 rounded-lg border border-border-subtle px-3 py-2"><Search size={15} className="text-muted" /><input aria-label={t("knowledge.search")} placeholder={t("knowledge.search")} value={query} onChange={(e) => setQuery(e.target.value)} className="w-full bg-transparent text-[13px] text-primary outline-none" /></div>
        <select aria-label={t("knowledge.projects")} value={project} onChange={(e) => setProject(e.target.value)} className="max-w-64 rounded-lg border border-border-subtle bg-surface px-3 py-2 text-[13px] text-secondary"><option value="">{t("knowledge.projects")}</option>{projects.map(([path, name]) => <option key={path} value={path}>{name} — {path}</option>)}</select>
        <select aria-label={t("knowledge.categories")} value={category} onChange={(e) => setCategory(e.target.value)} className="rounded-lg border border-border-subtle bg-surface px-3 py-2 text-[13px] text-secondary"><option value="">{t("knowledge.categories")}</option>{categories.map((name) => <option key={name} value={name}>{name}</option>)}</select>
        <span className="text-[12px] text-muted">{t("knowledge.count", { count: filtered.length, projects: projects.length })}</span>
      </div>
      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-[minmax(240px,1fr)_minmax(0,2fr)]">
        <div className="min-h-0 overflow-auto rounded-xl border border-border-subtle bg-surface">
          {filtered.length === 0 && <p className="p-6 text-[13px] text-muted">{t(busy ? "knowledge.scanning" : scannedRoot ? "knowledge.empty" : "knowledge.start")}</p>}
          {filtered.map((document) => <button key={document.path} disabled={busy} onClick={() => select(document)} className={cn("block w-full border-b border-border-subtle p-4 text-left hover:bg-surface-hover", selected?.path === document.path && "bg-accent-bg")}>
            <p className="text-[14px] font-medium text-primary">{document.title}</p>
            <p className="mt-1 text-[12px] text-muted">{document.project_name} · {document.category}</p>
            {document.description && <p className="mt-2 line-clamp-2 text-[12px] text-secondary">{document.description}</p>}
            <p className="mt-2 break-all text-[11px] text-muted">{document.relative_path}</p>
          </button>)}
        </div>
        <div className="min-h-0 overflow-auto rounded-xl border border-border-subtle bg-surface p-5">
          {!selected ? <p className="text-[13px] text-muted">{t("knowledge.select")}</p> : <>
            <div className="mb-5 border-b border-border-subtle pb-4">
              <div className="flex items-start justify-between gap-3"><h2 className="text-[14px] font-semibold text-primary">{selected.title}</h2><button onClick={() => setRaw(!raw)} className="shrink-0 rounded-md border border-border-subtle px-2 py-1 text-[12px] text-secondary">{t(raw ? "knowledge.preview" : "knowledge.raw")}</button></div>
              <p className="mt-2 break-all text-[12px] text-muted">{selected.path}</p>
              {selected.modified_at !== null && <p className="mt-1 text-[12px] text-muted">{t("knowledge.modified")} {new Date(selected.modified_at * 1000).toLocaleString()}</p>}
            </div>
            {documentError ? <p role="alert" className="text-[13px] text-danger">{documentError}</p> : content === null ? <p className="text-[13px] text-muted">{t("knowledge.loading")}</p> : raw ? <pre className="whitespace-pre-wrap break-words text-[13px] text-secondary">{content}</pre> : <SkillMarkdown content={content} />}
          </>}
        </div>
      </div>
    </div>
  );
}
