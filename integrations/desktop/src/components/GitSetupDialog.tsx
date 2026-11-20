import { useState } from "react";
import { X, Cloud, Upload } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "../utils";

interface Props {
  open: boolean;
  hasRemote: boolean;
  onClose: () => void;
  onClone: () => Promise<void>;
  onInit: () => Promise<void>;
}

type Choice = "clone" | "init";

export function GitSetupDialog({ open, hasRemote, onClose, onClone, onInit }: Props) {
  const { t } = useTranslation();
  const [choice, setChoice] = useState<Choice>("clone");
  const [loading, setLoading] = useState(false);

  if (!open) return null;

  const handleConfirm = async () => {
    if (!hasRemote) return;
    setLoading(true);
    try {
      if (choice === "clone") {
        await onClone();
      } else {
        await onInit();
      }
      onClose();
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={() => !loading && onClose()} />
      <div className="relative bg-surface border border-border rounded-xl w-full max-w-lg p-5 shadow-2xl">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h2 className="text-[14px] font-semibold text-primary">{t("settings.gitSetupTitle")}</h2>
            <p className="mt-1 text-[12px] text-muted">{t("settings.gitSetupSubtitle")}</p>
          </div>
          <button
            onClick={() => !loading && onClose()}
            disabled={loading}
            className="text-muted hover:text-secondary p-1 rounded-md transition-colors outline-none"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {!hasRemote && (
          <div className="mb-4 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-[12px] text-amber-600 dark:text-amber-400">
            {t("settings.gitSetupNeedRemote")}
          </div>
        )}

        <div className="space-y-2">
          <ChoiceCard
            icon={<Cloud className="h-4 w-4" />}
            active={choice === "clone"}
            disabled={!hasRemote || loading}
            badge={t("settings.gitSetupCardCloneBadge")}
            title={t("settings.gitSetupCardCloneTitle")}
            description={t("settings.gitSetupCardCloneDesc")}
            onClick={() => setChoice("clone")}
          />
          <ChoiceCard
            icon={<Upload className="h-4 w-4" />}
            active={choice === "init"}
            disabled={!hasRemote || loading}
            badge={t("settings.gitSetupCardInitBadge")}
            title={t("settings.gitSetupCardInitTitle")}
            description={t("settings.gitSetupCardInitDesc")}
            onClick={() => setChoice("init")}
          />
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={() => !loading && onClose()}
            disabled={loading}
            className="px-3 py-1.5 rounded-lg text-[13px] font-medium text-tertiary hover:text-secondary hover:bg-surface-hover transition-colors outline-none disabled:opacity-50"
          >
            {t("common.cancel")}
          </button>
          <button
            onClick={handleConfirm}
            disabled={loading || !hasRemote}
            className="px-3 py-1.5 rounded-lg bg-accent-dark hover:bg-accent text-white text-[13px] font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed border border-accent-border outline-none"
          >
            {loading ? t("common.loading") : t("settings.gitSetupConfirm")}
          </button>
        </div>
      </div>
    </div>
  );
}

interface CardProps {
  icon: React.ReactNode;
  active: boolean;
  disabled: boolean;
  badge: string;
  title: string;
  description: string;
  onClick: () => void;
}

function ChoiceCard({ icon, active, disabled, badge, title, description, onClick }: CardProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "w-full text-left rounded-md border px-3 py-3 transition-colors outline-none",
        "disabled:cursor-not-allowed disabled:opacity-60",
        active
          ? "border-accent bg-accent-bg"
          : "border-border-subtle bg-bg-secondary hover:bg-surface-hover"
      )}
    >
      <div className="flex items-center gap-2">
        <span className={cn("rounded-full p-1", active ? "bg-accent/20 text-accent-light" : "bg-surface text-muted")}>{icon}</span>
        <span className="text-[13px] font-semibold text-primary">{title}</span>
        <span className="ml-auto rounded-full border border-border-subtle bg-surface px-2 py-0.5 text-[11px] text-muted">
          {badge}
        </span>
      </div>
      <p className="mt-1.5 pl-7 text-[12px] text-tertiary leading-relaxed">{description}</p>
    </button>
  );
}
