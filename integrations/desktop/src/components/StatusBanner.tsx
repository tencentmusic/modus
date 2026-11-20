import { AlertTriangle, RefreshCw } from "lucide-react";
import { cn } from "../utils";

interface StatusBannerProps {
  title: string;
  description?: string;
  actionLabel?: string;
  onAction?: () => void;
  tone?: "warning" | "danger";
  compact?: boolean;
}

export function StatusBanner({
  title,
  description,
  actionLabel,
  onAction,
  tone = "warning",
  compact = false,
}: StatusBannerProps) {
  const toneClass =
    tone === "danger"
      ? "border-red-500/25 bg-red-500/10"
      : "border-amber-500/25 bg-amber-500/10";

  const iconClass = tone === "danger" ? "text-red-600 dark:text-red-300" : "text-amber-600 dark:text-amber-300";

  return (
    <div
      className={cn(
        "rounded-xl border px-4 py-3 dark:shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]",
        toneClass,
        compact && "px-3.5 py-3"
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 gap-3">
          <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-black/10">
            <AlertTriangle className={cn("h-4 w-4", iconClass)} />
          </div>
          <div className="min-w-0">
            <p className="text-[13px] font-semibold text-primary">{title}</p>
            {description ? (
              <p className="mt-1 text-[13px] leading-5 text-muted">{description}</p>
            ) : null}
          </div>
        </div>

        {actionLabel && onAction ? (
          <button
            type="button"
            onClick={onAction}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-black/10 bg-black/10 dark:border-white/10 px-3 py-1.5 text-[13px] font-medium text-primary transition-colors hover:bg-black/20"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            {actionLabel}
          </button>
        ) : null}
      </div>
    </div>
  );
}
