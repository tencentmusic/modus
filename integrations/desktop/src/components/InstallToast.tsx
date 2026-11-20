import { Check, GitBranch, Download, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";

export type InstallPhase = "cloning" | "installing" | "syncing" | "done";

interface InstallToastProps {
  skillName: string;
  phase: InstallPhase;
}

const phaseConfig: Record<
  InstallPhase,
  { icon: typeof Loader2; i18nKey: string; spinning: boolean }
> = {
  cloning: { icon: GitBranch, i18nKey: "install.toast.cloning", spinning: true },
  installing: { icon: Download, i18nKey: "install.toast.installing", spinning: true },
  syncing: { icon: Loader2, i18nKey: "install.toast.syncing", spinning: true },
  done: { icon: Check, i18nKey: "install.toast.done", spinning: false },
};

export function InstallToast({ skillName, phase }: InstallToastProps) {
  const { t } = useTranslation();
  const config = phaseConfig[phase];
  const Icon = config.icon;

  return (
    <div className="flex items-center gap-2.5">
      <div className="flex h-5 w-5 shrink-0 items-center justify-center">
        {config.spinning ? (
          <Loader2 className="h-4 w-4 animate-spin text-accent" />
        ) : (
          <Icon className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
        )}
      </div>
      <span className="text-[13px] text-secondary">
        {t(config.i18nKey, { name: skillName })}
      </span>
    </div>
  );
}
