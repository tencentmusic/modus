import { useState } from "react";
import { X, AlertTriangle, RotateCcw, GitBranch } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { cn } from "../utils";
import type { GitUpstreamHealth } from "../lib/tauri";

type RecoveryReason = GitUpstreamHealth | "conflict";

interface Props {
  open: boolean;
  reason: RecoveryReason;
  onClose: () => void;
  onReclone: () => Promise<void>;
}

export function GitRecoveryDialog({ open, reason, onClose, onReclone }: Props) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState<"reclone" | null>(null);

  if (!open) return null;

  // A conflict is already aborted by the backend; re-cloning is the only safe
  // in-app fix, so we hide the "keep local" path for it.
  const isConflict = reason === "conflict";
  const subtitleKey =
    reason === "conflict"
      ? "settings.gitRecoverySubtitleConflict"
      : reason === "unrelated_histories"
        ? "settings.gitRecoverySubtitleUnrelated"
        : reason === "no_upstream"
          ? "settings.gitRecoverySubtitleNoUpstream"
          : "settings.gitRecoverySubtitleDetached";

  const handleReclone = async () => {
    setLoading("reclone");
    try {
      await onReclone();
      onClose();
    } finally {
      setLoading(null);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={() => !loading && onClose()} />
      <div className="relative bg-surface border border-border rounded-xl w-full max-w-lg p-5 shadow-2xl">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2 text-[14px] font-semibold text-primary">
              <AlertTriangle className="h-4 w-4 text-red-500" />
              {t("settings.gitRecoveryTitle")}
            </h2>
            <p className="mt-1 text-[12px] text-muted leading-relaxed">{t(subtitleKey)}</p>
          </div>
          <button
            onClick={() => !loading && onClose()}
            disabled={!!loading}
            className="text-muted hover:text-secondary p-1 rounded-md transition-colors outline-none"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="space-y-2">
          <button
            type="button"
            onClick={handleReclone}
            disabled={!!loading}
            className={cn(
              "w-full text-left rounded-md border border-accent bg-accent-bg px-3 py-3 transition-colors outline-none",
              "disabled:cursor-not-allowed disabled:opacity-60 hover:bg-accent-bg/80"
            )}
          >
            <div className="flex items-center gap-2">
              <span className="rounded-full bg-accent/20 p-1 text-accent-light">
                <RotateCcw className="h-4 w-4" />
              </span>
              <span className="text-[13px] font-semibold text-primary">
                {loading === "reclone"
                  ? t("settings.gitRecoveryRecloning")
                  : t("settings.gitRecoveryCardRecloneTitle")}
              </span>
            </div>
            <p className="mt-1.5 pl-7 text-[12px] text-tertiary leading-relaxed">
              {t("settings.gitRecoveryCardRecloneDesc")}
            </p>
          </button>

          {!isConflict && (
            <button
              type="button"
              onClick={() => toast.info(t("settings.gitRecoveryFallbackHint"))}
              disabled={!!loading}
              className="w-full text-left rounded-md border border-border-subtle bg-bg-secondary px-3 py-3 transition-colors outline-none hover:bg-surface-hover disabled:cursor-not-allowed disabled:opacity-60"
            >
              <div className="flex items-center gap-2">
                <span className="rounded-full bg-surface p-1 text-muted">
                  <GitBranch className="h-4 w-4" />
                </span>
                <span className="text-[13px] font-semibold text-primary">
                  {t("settings.gitRecoveryCardKeepLocalTitle")}
                </span>
              </div>
              <p className="mt-1.5 pl-7 text-[12px] text-tertiary leading-relaxed">
                {t("settings.gitRecoveryCardKeepLocalDesc")}
              </p>
            </button>
          )}
        </div>

        <div className="mt-5 flex justify-end">
          <button
            onClick={() => !loading && onClose()}
            disabled={!!loading}
            className="px-3 py-1.5 rounded-lg text-[13px] font-medium text-tertiary hover:text-secondary hover:bg-surface-hover transition-colors outline-none disabled:opacity-50"
          >
            {t("common.cancel")}
          </button>
        </div>
      </div>
    </div>
  );
}
