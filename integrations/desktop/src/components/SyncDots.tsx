import { useState } from "react";
import { ChevronUp, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ManagedSkill, ToolInfo } from "../lib/tauri";
import { cn } from "../utils";
import { AgentIcon } from "./AgentIcon";
import { hasAgentIcon } from "../lib/agentIcons";

function shortLabel(displayName: string, key: string): string {
  const words = displayName.trim().split(/\s+/).filter(Boolean);
  if (words.length >= 2) {
    return (words[0][0] + words[1][0]).toUpperCase();
  }
  const word = words[0] || key;
  return word.slice(0, 2).toUpperCase();
}

type DotState = "synced" | "available" | "orphan";

interface Dot {
  key: string;
  displayName: string;
  state: DotState;
}

interface Props {
  skill: ManagedSkill;
  tools: ToolInfo[];
  limit?: number;
  size?: "sm" | "md";
  className?: string;
  /**
   * When true, also surface skill targets whose agent is no longer installed/enabled
   * (e.g. CLI uninstalled or disabled in Settings) so the indicator does not silently
   * disappear while the store still treats the skill as synced.
   */
  includeOrphan?: boolean;
  /**
   * When provided, each agent dot becomes a button: clicking syncs/unsyncs the
   * skill from that agent. The handler receives the next desired state.
   */
  onToggle?: (toolKey: string, enabled: boolean) => void;
  /** Tool key currently performing a sync/unsync operation; shows a loader on that dot. */
  pendingKey?: string | null;
}

export function SyncDots({
  skill,
  tools,
  limit,
  size = "md",
  className,
  includeOrphan = false,
  onToggle,
  pendingKey,
}: Props) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const syncedKeys = new Set(skill.targets.map((t) => t.tool));
  const activeTools = tools.filter((t) => t.installed && t.enabled);
  const activeKeys = new Set(activeTools.map((t) => t.key));

  const dots: Dot[] = activeTools.map((tool) => ({
    key: tool.key,
    displayName: tool.display_name,
    state: syncedKeys.has(tool.key) ? "synced" : "available",
  }));

  if (includeOrphan) {
    for (const target of skill.targets) {
      if (activeKeys.has(target.tool)) continue;
      const known = tools.find((t) => t.key === target.tool);
      dots.push({
        key: target.tool,
        displayName: known?.display_name || target.tool,
        state: "orphan",
      });
    }
  }

  const collapsedDots = typeof limit === "number" ? dots.slice(0, limit) : dots;
  const hiddenCount = dots.length - collapsedDots.length;
  const visible = onToggle && expanded ? dots : collapsedDots;

  const dim = size === "sm"
    ? "h-[16px] w-[16px] text-[8px]"
    : "h-[18px] w-[18px] text-[9px]";

  const iconStateClass: Record<DotState, string> = {
    synced: "bg-surface",
    available: "bg-surface opacity-45",
    orphan: "ring-1 ring-inset ring-amber-500/60 bg-surface",
  };

  const textStateClass: Record<DotState, string> = {
    synced: "border-transparent bg-[var(--color-text-primary)] text-[var(--color-bg)]",
    available: "border border-border-subtle bg-surface-hover text-faint",
    orphan: "border border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-400",
  };

  const stateTitle: Record<DotState, string> = {
    synced: " · synced",
    available: "",
    orphan: " · synced · agent unavailable",
  };

  const clickHint: Record<DotState, string> = {
    synced: ` · ${t("mySkills.targetClickUninstall")}`,
    available: ` · ${t("mySkills.targetClickInstall")}`,
    orphan: ` · ${t("mySkills.targetClickUninstall")}`,
  };

  return (
    <div className={cn("flex items-center gap-[2px]", onToggle && expanded && "max-w-[160px] flex-wrap", className)}>
      {visible.map((dot) => {
        const useIcon = hasAgentIcon(dot.key);
        const isPending = pendingKey === dot.key;
        const interactive = !!onToggle && !isPending;
        const title = `${dot.displayName}${stateTitle[dot.state]}${onToggle ? clickHint[dot.state] : ""}`;
        const baseClass = cn(
          "inline-flex shrink-0 select-none items-center justify-center overflow-hidden rounded-[4px] transition-colors",
          dim,
          useIcon ? iconStateClass[dot.state] : cn("border font-mono font-semibold tracking-tight", textStateClass[dot.state]),
          interactive && "cursor-pointer hover:ring-1 hover:ring-accent/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
          isPending && "opacity-70",
        );
        const content = isPending ? (
          <Loader2 className="h-3 w-3 animate-spin text-muted" />
        ) : useIcon ? (
          <AgentIcon
            agentKey={dot.key}
            className="h-full w-full rounded-[4px] border-0 bg-transparent"
          />
        ) : (
          shortLabel(dot.displayName, dot.key)
        );

        if (onToggle) {
          return (
            <button
              type="button"
              key={dot.key}
              title={title}
              aria-label={title}
              disabled={isPending}
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                onToggle(dot.key, dot.state === "available");
              }}
              className={baseClass}
            >
              {content}
            </button>
          );
        }

        return (
          <span key={dot.key} title={title} className={baseClass}>
            {content}
          </span>
        );
      })}
      {hiddenCount > 0 && (onToggle ? (
        <button
          type="button"
          title={t(expanded ? "common.collapse" : "common.expandAll")}
          aria-label={t(expanded ? "common.collapse" : "common.expandAll")}
          aria-expanded={expanded}
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            setExpanded((value) => !value);
          }}
          className={cn(
            "inline-flex shrink-0 select-none items-center justify-center rounded-[4px] border border-border-subtle bg-surface-hover font-mono font-semibold text-faint hover:ring-1 hover:ring-accent/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
            dim,
          )}
        >
          {expanded ? <ChevronUp className="h-3 w-3" /> : `+${hiddenCount}`}
        </button>
      ) : (
        <span
          title={`+${hiddenCount} more agents`}
          className={cn(
            "inline-flex shrink-0 select-none items-center justify-center rounded-[4px] border border-border-subtle bg-surface-hover font-mono font-semibold text-faint",
            dim,
          )}
        >
          +{hiddenCount}
        </span>
      ))}
    </div>
  );
}
