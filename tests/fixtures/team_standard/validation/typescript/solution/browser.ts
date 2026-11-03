import { LookupClient, normalizeIds } from "../ports";

export type View = { kind: "ready"; value: string } | { kind: "failed"; error: unknown };

export function createLookup(client: LookupClient, publish: (view: View) => void) {
  let requestVersion = 0;
  let currentController: AbortController | undefined;
  let stopped = false;
  return {
    async load(id: string): Promise<void> {
      normalizeIds([id]);
      if (stopped) {
        throw new Error("lookup stopped");
      }
      const version = ++requestVersion;
      currentController?.abort();
      const controller = new AbortController();
      currentController = controller;
      let view: View;
      try {
        view = { kind: "ready", value: await client.lookup(id, controller.signal) };
      } catch (error) {
        view = { kind: "failed", error };
      }
      // client 可能忽略取消；序号独立阻止旧结果和旧错误覆盖当前状态。
      if (version === requestVersion && !stopped) {
        publish(view);
      }
    },
    stop(): void {
      stopped = true;
      requestVersion++;
      currentController?.abort();
    },
  };
}
