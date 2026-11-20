import type { ManagedSkill } from "./tauri";

export type PickerStatus = "available" | "installed" | "conflict" | "unavailable";

export interface GlobalPickerContext {
  kind: "global";
  installedSkillIds: Set<string>;
}

export interface ProjectPickerContext {
  kind: "project";
  selectedAgents: string[];
  projectSkillDirNamesByAgent: Record<string, string[]>;
  projectCenterSkillIdsByAgent: Record<string, string[]>;
  dirNameMap: Record<string, string>;
  dirNameMapError: boolean;
}

export type PickerContext = GlobalPickerContext | ProjectPickerContext;

export function classifySkill(skill: ManagedSkill, ctx: PickerContext): PickerStatus {
  if (ctx.kind === "global") {
    return ctx.installedSkillIds.has(skill.id) ? "installed" : "available";
  }

  if (ctx.selectedAgents.length === 0) return "unavailable";

  const allInstalled = ctx.selectedAgents.every((agent) => {
    const installed = ctx.projectCenterSkillIdsByAgent[agent] ?? [];
    return installed.includes(skill.id);
  });
  if (allInstalled) return "installed";

  const dirName = ctx.dirNameMap[skill.id]?.toLowerCase();
  if (ctx.dirNameMapError && !dirName) return "conflict";

  const anyConflict = ctx.selectedAgents.some((agent) => {
    const installed = ctx.projectCenterSkillIdsByAgent[agent] ?? [];
    if (installed.includes(skill.id)) return false;
    if (!dirName) return false;
    const dirNames = ctx.projectSkillDirNamesByAgent[agent] ?? [];
    return dirNames.includes(dirName);
  });
  if (anyConflict) return "conflict";

  return "available";
}

export function targetsToInstall(
  skill: ManagedSkill,
  ctx: ProjectPickerContext,
): string[] {
  return ctx.selectedAgents.filter((agent) => {
    const installed = ctx.projectCenterSkillIdsByAgent[agent] ?? [];
    return !installed.includes(skill.id);
  });
}
