import type { ManagedSkill, Preset } from "./tauri";

export type PresetStatus = "active" | "partial" | "inactive" | "empty";

export interface PresetStatusResult {
  status: PresetStatus;
  installed: number;
  total: number;
}

/** Granularity of the preset status tally. */
export type PresetStatusMode = "agent-pair" | "logical-skill";

/** How much of a preset is installed in the current workspace. */
export function computePresetStatus(
  preset: Preset,
  skills: ManagedSkill[],
  agentKeys: string[],
  existsInWorkspace: (skill: ManagedSkill, agentKey: string) => boolean,
  mode: PresetStatusMode = "agent-pair"
): PresetStatusResult {
  const presetSkills = skills.filter((s) => s.preset_ids.includes(preset.id));
  if (presetSkills.length === 0 || agentKeys.length === 0) {
    return { status: "empty", installed: 0, total: 0 };
  }
  if (mode === "logical-skill") {
    const total = presetSkills.length;
    let installed = 0;
    let anyCopy = false;
    for (const skill of presetSkills) {
      const deployed = agentKeys.filter((agentKey) => existsInWorkspace(skill, agentKey)).length;
      if (deployed > 0) anyCopy = true;
      if (deployed === agentKeys.length) installed++;
    }
    if (installed === total) return { status: "active", installed, total };
    // A skill that reached some of the project's agents but not all of them
    // is not installed — but it is not absent either. Reporting it inactive
    // would hide a half-applied preset behind the same grey pill as one that
    // was never applied at all.
    if (!anyCopy) return { status: "inactive", installed, total };
    return { status: "partial", installed, total };
  }

  const total = presetSkills.length * agentKeys.length;
  let installed = 0;
  for (const skill of presetSkills) {
    for (const agentKey of agentKeys) {
      if (existsInWorkspace(skill, agentKey)) installed++;
    }
  }
  if (installed === total) return { status: "active", installed, total };
  if (installed === 0) return { status: "inactive", installed, total };
  return { status: "partial", installed, total };
}
