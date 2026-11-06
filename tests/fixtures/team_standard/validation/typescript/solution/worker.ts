import { normalizeIds, WorkerPorts } from "../ports";

export async function reserve(
  ports: WorkerPorts,
  tenant: string,
  ids: readonly string[],
): Promise<string[]> {
  if (!tenant) {
    throw new Error("tenant required");
  }
  const unique = normalizeIds(ids);
  const { window } = ports.readPolicy();
  if (!Number.isSafeInteger(window) || window <= 0) {
    throw new Error("invalid window");
  }
  return ports.mapWindow(unique, window, async id => {
    if (!await ports.updateIfPending(tenant, id)) {
      throw new Error("reservation conflict");
    }
    return id;
  });
}
