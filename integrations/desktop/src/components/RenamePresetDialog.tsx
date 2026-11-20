import { useState, useEffect } from "react";
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "../utils";
import { PRESET_ICON_OPTIONS, getPresetIconOption } from "../lib/presetIcons";

interface Props {
  open: boolean;
  currentName: string;
  currentIcon?: string | null;
  currentDescription?: string | null;
  onClose: () => void;
  onRename: (newName: string, icon?: string, description?: string) => Promise<void>;
}

export function RenamePresetDialog({
  open,
  currentName,
  currentIcon,
  currentDescription,
  onClose,
  onRename,
}: Props) {
  const { t } = useTranslation();
  // The icon the sidebar actually shows — inferred from the name when none is stored.
  const shownIcon = getPresetIconOption({
    name: currentName,
    description: currentDescription ?? null,
    icon: currentIcon ?? null,
  }).key;
  const [name, setName] = useState(currentName);
  const [icon, setIcon] = useState(shownIcon);
  const [description, setDescription] = useState(currentDescription || "");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (open) {
      setName(currentName);
      setIcon(shownIcon);
      setDescription(currentDescription || "");
    }
  }, [open, shownIcon, currentName, currentDescription]);

  if (!open) return null;

  const unchanged =
    name.trim() === currentName &&
    icon === shownIcon &&
    description.trim() === (currentDescription || "").trim();

  const handleRename = async () => {
    if (!name.trim() || unchanged) {
      return;
    }
    setLoading(true);
    try {
      // Only send an icon the user picked: saving a name or description must
      // not pin the inferred icon of a preset that has none stored.
      await onRename(
        name.trim(),
        icon !== shownIcon ? icon : currentIcon || undefined,
        description.trim() || undefined,
      );
      onClose();
    } finally {
      setLoading(false);
    }
  };

  const inputClass = "w-full bg-background border border-border-subtle rounded-lg px-3 py-2 text-[13px] text-secondary focus:outline-none focus:border-border transition-all placeholder-faint";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-surface border border-border rounded-xl w-full max-w-[400px] p-5 shadow-2xl">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-[13px] font-semibold text-primary">{t("common.edit")}</h2>
          <button onClick={onClose} className="text-muted hover:text-secondary p-1 rounded-md transition-colors outline-none">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="space-y-3">
          <div>
            <label className="block text-[13px] font-medium text-tertiary mb-1">{t("preset.name")}</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("preset.namePlaceholder")}
              className={inputClass}
              autoFocus
              onKeyDown={(e) => e.key === "Enter" && handleRename()}
            />
          </div>
          <div>
            <label className="block text-[13px] font-medium text-tertiary mb-1">{t("preset.description")}</label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={t("preset.descPlaceholder")}
              className={inputClass}
              onKeyDown={(e) => e.key === "Enter" && handleRename()}
            />
          </div>
          <div>
            <label className="block text-[13px] font-medium text-tertiary mb-1.5">{t("preset.icon")}</label>
            <div className="grid max-h-[220px] grid-cols-[repeat(auto-fill,minmax(36px,1fr))] gap-1.5 overflow-y-auto pr-1">
              {PRESET_ICON_OPTIONS.map((option) => {
                const Icon = option.icon;
                const selected = option.key === icon;
                return (
                  <button
                    key={option.key}
                    type="button"
                    onClick={() => setIcon(option.key)}
                    className={cn(
                      "flex h-9 items-center justify-center rounded-lg border bg-background transition-all outline-none",
                      selected
                        ? `${option.activeClass} ${option.colorClass}`
                        : "border-border-subtle text-muted hover:border-border hover:text-secondary"
                    )}
                    title={option.label}
                  >
                    <Icon className="h-3.5 w-3.5" />
                  </button>
                );
              })}
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <button
              onClick={onClose}
              className="px-3 py-1.5 rounded-lg text-[13px] font-medium text-tertiary hover:text-secondary hover:bg-surface-hover transition-colors outline-none"
            >
              {t("common.cancel")}
            </button>
            <button
              onClick={handleRename}
              disabled={!name.trim() || unchanged || loading}
              className="px-3 py-1.5 rounded-lg bg-accent-dark hover:bg-accent text-white text-[13px] font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed border border-accent-border outline-none"
            >
              {loading ? t("common.loading") : t("common.save")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
