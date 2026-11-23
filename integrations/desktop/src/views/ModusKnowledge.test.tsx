// @vitest-environment jsdom
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, mount } from "../test-utils/mount";
import { ModusKnowledge } from "./ModusKnowledge";
import * as api from "../lib/tauri";

vi.mock("../lib/tauri", () => ({
  getSettings: vi.fn(), setSettings: vi.fn(), scanModusKnowledge: vi.fn(), getModusKnowledgeDocument: vi.fn(),
}));
vi.mock("@tauri-apps/plugin-dialog", () => ({ open: vi.fn() }));
vi.mock("react-i18next", () => {
  const t = (key: string) => key;
  return { useTranslation: () => ({ t }) };
});
vi.mock("../components/SkillMarkdown", () => ({ SkillMarkdown: ({ content }: { content: string }) => <article>{content}</article> }));
const document = (name: string, category = "domain"): api.KnowledgeDocument => ({
  path: `/workspace/app/modus/knowledge/${name}.md`, relative_path: `${name}.md`, project_name: "app", project_path: "/workspace/app",
  title: name, category, description: null, modified_at: 0,
});
const flush = () => act(async () => { await Promise.resolve(); });
function button(node: HTMLElement, text: string) {
  return Array.from(node.querySelectorAll("button")).find((b) => b.textContent?.includes(text))!;
}
function branch(node: HTMLElement, label: string) {
  return Array.from(node.querySelectorAll("summary")).find((summary) => summary.textContent === label)!
    .parentElement as HTMLDetailsElement;
}
function search(node: HTMLElement, value: string) {
  const input = node.querySelector('input[aria-label="knowledge.search"]') as HTMLInputElement;
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}
async function scan(node: HTMLElement) {
  await act(async () => { button(node, "knowledge.scan").click(); });
}

afterEach(cleanup);
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.getSettings).mockResolvedValue("/workspace");
  vi.mocked(api.setSettings).mockResolvedValue(undefined);
  vi.mocked(api.scanModusKnowledge).mockResolvedValue({ documents: [document("Orders"), document("Rules", "constraint")], warnings: [] });
  vi.mocked(api.getModusKnowledgeDocument).mockResolvedValue("# Document body");
});

describe("Modus knowledge browser", () => {
  it("waits for a workspace choice on a fresh install", async () => {
    vi.mocked(api.getSettings).mockResolvedValue(null);
    const node = mount(<ModusKnowledge />);
    await flush();
    expect(node.querySelector<HTMLInputElement>('input[aria-label="knowledge.root"]')?.value).toBe("");
    expect(button(node, "knowledge.scan").disabled).toBe(true);
    expect(api.scanModusKnowledge).not.toHaveBeenCalled();
  });

  it("scans the saved path, filters by category, and reads the selected original", async () => {
    const node = mount(<ModusKnowledge />);
    await flush(); await scan(node);
    expect(api.scanModusKnowledge).toHaveBeenCalledWith("/workspace", false);
    expect(api.setSettings).toHaveBeenCalledWith("modus_knowledge_root", "/workspace");
    const categories = node.querySelector('select[aria-label="knowledge.categories"]') as HTMLSelectElement;
    act(() => { categories.value = "constraint"; categories.dispatchEvent(new Event("change", { bubbles: true })); });
    expect(button(node, "Orders")).toBeUndefined();
    await act(async () => { button(node, "Rules").click(); });
    expect(api.getModusKnowledgeDocument).toHaveBeenCalledWith("/workspace", document("Rules").path);
    expect(node.querySelector("article")?.textContent).toBe("# Document body");
    act(() => button(node, "knowledge.raw").click());
    expect(node.querySelector("pre")?.textContent).toBe("# Document body");
  });

  it("searches document metadata after scanning without evaluation and test copies", async () => {
    const node = mount(<ModusKnowledge />);
    await flush();
    expect(node.querySelector('input[type="checkbox"]')).toBeNull();
    await scan(node);
    expect(api.scanModusKnowledge).toHaveBeenCalledWith("/workspace", false);
    search(node, "orders.md");
    expect(button(node, "Orders")).toBeDefined();
    expect(button(node, "Rules")).toBeUndefined();
  });

  it("keeps same-named projects separate and reveals only matching branches in the library tree", async () => {
    const relativePath = "domain/ai-resolution/references/business/scenario/index.md";
    const scenario = {
      ...document("Scenario"),
      path: `/workspace/app/modus/knowledge/${relativePath}`,
      relative_path: relativePath,
    };
    const snapshot = {
      ...scenario,
      path: `/workspace/snapshot/app/modus/knowledge/${relativePath}`,
      project_path: "/workspace/snapshot/app",
      title: "Snapshot scenario",
    };
    vi.mocked(api.scanModusKnowledge).mockResolvedValue({
      documents: [document("Overview", "overview"), scenario, snapshot],
      warnings: [],
    });
    const node = mount(<ModusKnowledge />);
    await flush(); await scan(node);

    const currentProject = branch(node, "app/workspace/app");
    const snapshotProject = branch(node, "app/workspace/snapshot/app");
    expect(currentProject.open).toBe(false);
    expect(snapshotProject.contains(button(node, "Snapshot scenario"))).toBe(true);
    act(() => currentProject.querySelector("summary")!.click());
    expect(currentProject.open).toBe(true);
    const library = branch(currentProject, "knowledge.library");
    expect(library.open).toBe(true);
    expect(library.contains(button(node, "Overview"))).toBe(true);
    expect(branch(library, "domain").open).toBe(false);

    search(node, "snapshot scenario");
    expect([...node.querySelectorAll("summary")].map((summary) => summary.textContent)).not.toContain("app/workspace/app");
    let matchingBranch = branch(node, "app/workspace/snapshot/app");
    expect(matchingBranch.open).toBe(true);
    for (const label of ["knowledge.library", "domain", "ai-resolution", "references", "business", "scenario"]) {
      matchingBranch = branch(matchingBranch, label);
      expect(matchingBranch.open).toBe(true);
    }
    const match = button(matchingBranch, "Snapshot scenario");
    await act(async () => match.click());
    expect(api.getModusKnowledgeDocument).toHaveBeenCalledWith("/workspace", snapshot.path);
    expect(node.querySelector("article")?.textContent).toBe("# Document body");
    act(() => match.click());
    expect(node.querySelector("article")?.textContent).toBe("# Document body");
  });

  it("ignores an older document response after another selection", async () => {
    let finish!: (text: string) => void;
    vi.mocked(api.getModusKnowledgeDocument).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
    const node = mount(<ModusKnowledge />);
    await flush(); await scan(node);
    act(() => button(node, "Orders").click());
    await act(async () => button(node, "Rules").click());
    await act(async () => finish("stale body"));
    expect(node.querySelector("article")?.textContent).toBe("# Document body");
  });

  it("shows scan failures instead of retaining stale results", async () => {
    const node = mount(<ModusKnowledge />);
    await flush(); await scan(node);
    vi.mocked(api.scanModusKnowledge).mockRejectedValue({ kind: "io", message: "Permission denied" });
    await scan(node);
    expect(node.querySelector('[role="alert"]')?.textContent).toBe("Permission denied");
    expect(button(node, "Orders")).toBeUndefined();
  });
});
