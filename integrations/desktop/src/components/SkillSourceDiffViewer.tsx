import { useTranslation } from "react-i18next";
import { cn } from "../utils";
import { DocumentDiffViewer } from "./DocumentDiffViewer";
import type { SkillSourceDiffEntry } from "../lib/tauri";

interface Props {
  entries: SkillSourceDiffEntry[];
  className?: string;
}

const STATUS_TONE: Record<SkillSourceDiffEntry["status"], string> = {
  added: "border-emerald-300 bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300",
  removed: "border-red-300 bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-300",
  modified: "border-sky-300 bg-sky-50 text-sky-700 dark:bg-sky-950/40 dark:text-sky-300",
};

export function SkillSourceDiffViewer({ entries, className }: Props) {
  const { t } = useTranslation();

  if (entries.length === 0) {
    return (
      <div className={cn("rounded-xl border border-border-subtle bg-bg-secondary px-4 py-6 text-center", className)}>
        <div className="text-[13px] font-medium text-secondary">{t("mySkills.sourceDiff.noChanges")}</div>
      </div>
    );
  }

  return (
    <div className={cn("space-y-4", className)}>
      {entries.map((entry) => (
        <div key={entry.relative_path} className="overflow-hidden rounded-xl border border-border-subtle">
          <div className="flex flex-wrap items-center gap-2 border-b border-border-subtle bg-surface px-3 py-2">
            <span
              className={cn(
                "inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium",
                STATUS_TONE[entry.status]
              )}
            >
              {t(`mySkills.sourceDiff.status.${entry.status}`)}
            </span>
            <span className="min-w-0 flex-1 truncate font-mono text-[13px] text-secondary" title={entry.relative_path}>
              {entry.relative_path}
            </span>
            {entry.status === "modified" && entry.executable_before !== entry.executable_after && (
              <span className="inline-flex items-center rounded-full border border-border-subtle bg-bg-secondary px-2 py-0.5 text-[11px] text-muted">
                {t("mySkills.sourceDiff.execBit", {
                  before: entry.executable_before ? "0755" : "0644",
                  after: entry.executable_after ? "0755" : "0644",
                })}
              </span>
            )}
          </div>

          {entry.content_kind === "text" ? (
            <DocumentDiffViewer
              original={entry.original_text ?? ""}
              updated={entry.updated_text ?? ""}
              className="!space-y-0 !rounded-none !border-0"
            />
          ) : (
            <div className="px-4 py-4 text-[12px] text-muted">
              {t(`mySkills.sourceDiff.summary.${entry.content_kind}`)}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
