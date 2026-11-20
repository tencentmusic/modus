import type { LucideIcon } from "lucide-react";
import {
  Blocks,
  BookOpen,
  Bot,
  Brain,
  Briefcase,
  Bug,
  Calendar,
  ChartBar,
  Cloud,
  Code2,
  Cpu,
  Database,
  FlaskConical,
  FolderGit2,
  Heart,
  Home,
  Lightbulb,
  Lock,
  NotebookPen,
  Palette,
  Plane,
  Rocket,
  Search,
  Server,
  Shield,
  Sparkles,
  Star,
  Target,
  Terminal,
  Wrench,
  Zap,
} from "lucide-react";
import type { Preset } from "./tauri";

export interface PresetIconOption {
  key: string;
  label: string;
  icon: LucideIcon;
  colorClass: string;
  activeClass: string;
}

export const PRESET_ICON_OPTIONS: PresetIconOption[] = [
  {
    key: "briefcase",
    label: "Work",
    icon: Briefcase,
    colorClass: "text-amber-600 dark:text-amber-300",
    activeClass: "border-amber-500/30 bg-amber-500/12",
  },
  {
    key: "book-open",
    label: "Study",
    icon: BookOpen,
    colorClass: "text-emerald-600 dark:text-emerald-300",
    activeClass: "border-emerald-500/30 bg-emerald-500/12",
  },
  {
    key: "folder-git-2",
    label: "Open Source",
    icon: FolderGit2,
    colorClass: "text-rose-600 dark:text-rose-300",
    activeClass: "border-rose-500/30 bg-rose-500/12",
  },
  {
    key: "plane",
    label: "Travel",
    icon: Plane,
    colorClass: "text-yellow-600 dark:text-yellow-300",
    activeClass: "border-yellow-500/30 bg-yellow-500/12",
  },
  {
    key: "code-2",
    label: "Build",
    icon: Code2,
    colorClass: "text-cyan-600 dark:text-cyan-300",
    activeClass: "border-cyan-500/30 bg-cyan-500/12",
  },
  {
    key: "rocket",
    label: "Launch",
    icon: Rocket,
    colorClass: "text-orange-600 dark:text-orange-300",
    activeClass: "border-orange-500/30 bg-orange-500/12",
  },
  {
    key: "bot",
    label: "Agents",
    icon: Bot,
    colorClass: "text-indigo-600 dark:text-indigo-300",
    activeClass: "border-indigo-500/30 bg-indigo-500/12",
  },
  {
    key: "brain",
    label: "Thinking",
    icon: Brain,
    colorClass: "text-violet-600 dark:text-violet-300",
    activeClass: "border-violet-500/30 bg-violet-500/12",
  },
  {
    key: "terminal",
    label: "CLI",
    icon: Terminal,
    colorClass: "text-lime-600 dark:text-lime-300",
    activeClass: "border-lime-500/30 bg-lime-500/12",
  },
  {
    key: "database",
    label: "Data",
    icon: Database,
    colorClass: "text-blue-600 dark:text-blue-300",
    activeClass: "border-blue-500/30 bg-blue-500/12",
  },
  {
    key: "chart-bar",
    label: "Analytics",
    icon: ChartBar,
    colorClass: "text-sky-600 dark:text-sky-300",
    activeClass: "border-sky-500/30 bg-sky-500/12",
  },
  {
    key: "search",
    label: "Research",
    icon: Search,
    colorClass: "text-stone-600 dark:text-stone-300",
    activeClass: "border-stone-500/30 bg-stone-500/12",
  },
  {
    key: "sparkles",
    label: "Creative",
    icon: Sparkles,
    colorClass: "text-fuchsia-600 dark:text-fuchsia-300",
    activeClass: "border-fuchsia-500/30 bg-fuchsia-500/12",
  },
  {
    key: "lightbulb",
    label: "Ideas",
    icon: Lightbulb,
    colorClass: "text-yellow-600 dark:text-yellow-300",
    activeClass: "border-yellow-500/30 bg-yellow-500/12",
  },
  {
    key: "target",
    label: "Goals",
    icon: Target,
    colorClass: "text-red-600 dark:text-red-300",
    activeClass: "border-red-500/30 bg-red-500/12",
  },
  {
    key: "calendar",
    label: "Planning",
    icon: Calendar,
    colorClass: "text-slate-600 dark:text-slate-300",
    activeClass: "border-slate-500/30 bg-slate-500/12",
  },
  {
    key: "home",
    label: "Personal",
    icon: Home,
    colorClass: "text-green-600 dark:text-green-300",
    activeClass: "border-green-500/30 bg-green-500/12",
  },
  {
    key: "heart",
    label: "Health",
    icon: Heart,
    colorClass: "text-red-600 dark:text-red-300",
    activeClass: "border-red-500/30 bg-red-500/12",
  },
  {
    key: "star",
    label: "Favorites",
    icon: Star,
    colorClass: "text-amber-600 dark:text-amber-300",
    activeClass: "border-amber-500/30 bg-amber-500/12",
  },
  {
    key: "zap",
    label: "Automation",
    icon: Zap,
    colorClass: "text-yellow-600 dark:text-yellow-300",
    activeClass: "border-yellow-500/30 bg-yellow-500/12",
  },
  {
    key: "bug",
    label: "Debug",
    icon: Bug,
    colorClass: "text-red-600 dark:text-red-300",
    activeClass: "border-red-500/30 bg-red-500/12",
  },
  {
    key: "shield",
    label: "Security",
    icon: Shield,
    colorClass: "text-emerald-600 dark:text-emerald-300",
    activeClass: "border-emerald-500/30 bg-emerald-500/12",
  },
  {
    key: "lock",
    label: "Private",
    icon: Lock,
    colorClass: "text-neutral-600 dark:text-neutral-300",
    activeClass: "border-neutral-500/30 bg-neutral-500/12",
  },
  {
    key: "cloud",
    label: "Cloud",
    icon: Cloud,
    colorClass: "text-cyan-600 dark:text-cyan-300",
    activeClass: "border-cyan-500/30 bg-cyan-500/12",
  },
  {
    key: "server",
    label: "Infrastructure",
    icon: Server,
    colorClass: "text-slate-600 dark:text-slate-300",
    activeClass: "border-slate-500/30 bg-slate-500/12",
  },
  {
    key: "cpu",
    label: "Engineering",
    icon: Cpu,
    colorClass: "text-indigo-600 dark:text-indigo-300",
    activeClass: "border-indigo-500/30 bg-indigo-500/12",
  },
  {
    key: "flask-conical",
    label: "Experiment",
    icon: FlaskConical,
    colorClass: "text-purple-600 dark:text-purple-300",
    activeClass: "border-purple-500/30 bg-purple-500/12",
  },
  {
    key: "notebook-pen",
    label: "Notes",
    icon: NotebookPen,
    colorClass: "text-orange-600 dark:text-orange-300",
    activeClass: "border-orange-500/30 bg-orange-500/12",
  },
  {
    key: "blocks",
    label: "Systems",
    icon: Blocks,
    colorClass: "text-teal-600 dark:text-teal-300",
    activeClass: "border-teal-500/30 bg-teal-500/12",
  },
  {
    key: "palette",
    label: "Design",
    icon: Palette,
    colorClass: "text-pink-600 dark:text-pink-300",
    activeClass: "border-pink-500/30 bg-pink-500/12",
  },
  {
    key: "wrench",
    label: "Ops",
    icon: Wrench,
    colorClass: "text-zinc-600 dark:text-zinc-300",
    activeClass: "border-zinc-500/30 bg-zinc-500/10",
  },
];

const PRESET_ICON_MAP = new Map(
  PRESET_ICON_OPTIONS.map((option) => [option.key, option] as const)
);

const PRESET_KEYWORD_RULES: Array<{ key: string; keywords: string[] }> = [
  { key: "briefcase", keywords: ["工作", "work", "office", "client"] },
  { key: "book-open", keywords: ["学习", "study", "learn", "course", "research"] },
  { key: "folder-git-2", keywords: ["开源", "opensource", "open source", "github"] },
  { key: "plane", keywords: ["旅行", "travel", "trip", "holiday"] },
  { key: "code-2", keywords: ["开发", "code", "build", "app"] },
  { key: "bot", keywords: ["agent", "agents", "ai", "assistant", "机器人"] },
  { key: "brain", keywords: ["thinking", "reason", "brainstorm", "思考"] },
  { key: "terminal", keywords: ["cli", "terminal", "shell", "command", "命令行"] },
  { key: "database", keywords: ["data", "database", "sql", "数据"] },
  { key: "chart-bar", keywords: ["analytics", "metric", "report", "dashboard", "分析"] },
  { key: "search", keywords: ["research", "search", "调查", "检索"] },
  { key: "sparkles", keywords: ["creative", "content", "copy", "创意"] },
  { key: "target", keywords: ["goal", "target", "okr", "目标"] },
  { key: "calendar", keywords: ["plan", "planning", "schedule", "calendar", "计划"] },
  { key: "home", keywords: ["personal", "home", "life", "个人"] },
  { key: "heart", keywords: ["health", "fitness", "wellness", "健康"] },
  { key: "zap", keywords: ["automation", "automate", "workflow", "自动化"] },
  { key: "bug", keywords: ["debug", "bug", "fix", "修复"] },
  { key: "shield", keywords: ["security", "secure", "安全"] },
  { key: "cloud", keywords: ["cloud", "deploy", "云"] },
  { key: "server", keywords: ["infra", "infrastructure", "server", "ops", "运维"] },
  { key: "flask-conical", keywords: ["experiment", "lab", "test", "实验"] },
  { key: "notebook-pen", keywords: ["笔记", "note", "write", "journal"] },
  { key: "palette", keywords: ["设计", "design", "brand", "ui"] },
];

export function inferPresetIconKey(preset?: Pick<Preset, "name" | "description" | "icon"> | null) {
  if (preset?.icon && PRESET_ICON_MAP.has(preset.icon)) {
    return preset.icon;
  }

  const haystack = `${preset?.name || ""} ${preset?.description || ""}`.toLowerCase();
  const matched = PRESET_KEYWORD_RULES.find((rule) =>
    rule.keywords.some((keyword) => haystack.includes(keyword))
  );

  return matched?.key || "briefcase";
}

export function getPresetIconOption(
  preset?: Pick<Preset, "name" | "description" | "icon"> | string | null
) {
  const key =
    typeof preset === "string"
      ? preset
      : inferPresetIconKey(preset);
  return PRESET_ICON_MAP.get(key) || PRESET_ICON_OPTIONS[0];
}
