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

  it("searches document metadata and passes the snapshots option", async () => {
    const node = mount(<ModusKnowledge />);
    await flush();
    act(() => (node.querySelector('input[type="checkbox"]') as HTMLInputElement).click());
    await scan(node);
    expect(api.scanModusKnowledge).toHaveBeenCalledWith("/workspace", true);
    const input = node.querySelector('input[aria-label="knowledge.search"]') as HTMLInputElement;
    act(() => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, "orders.md");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(button(node, "Orders")).toBeDefined();
    expect(button(node, "Rules")).toBeUndefined();
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
