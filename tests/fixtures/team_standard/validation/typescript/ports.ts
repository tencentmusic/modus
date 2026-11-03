// 已有共享包，仅依赖 ES2020；信号只暴露本项目真正使用的最小协议。
export interface CancelSignal {
  readonly aborted: boolean;
}

export interface LookupClient {
  lookup(id: string, signal: CancelSignal): Promise<string>;
}

export function normalizeIds(ids: readonly string[]): string[] {
  // for...of 同时检查稀疏数组的空位，避免将 undefined 交给写入端口。
  for (const id of ids) {
    if (typeof id !== "string" || id.length === 0) {
      throw new Error("id required");
    }
  }
  return [...new Set(ids)];
}
export interface Policy {
  readonly window: number;
}

export interface WorkerPorts {
  readPolicy(): Policy;
  updateIfPending(tenant: string, id: string): Promise<boolean>;
  mapWindow<T, R>(
    items: readonly T[],
    window: number,
    work: (item: T) => Promise<R>,
  ): Promise<R[]>;
}

// 已有批量调度能力；一组完成才接收下一组，失败不回滚已完成项。
export async function mapWindow<T, R>(
  items: readonly T[],
  window: number,
  work: (item: T) => Promise<R>,
): Promise<R[]> {
  if (!Number.isSafeInteger(window) || window <= 0) {
    throw new Error("invalid window");
  }
  const results: R[] = [];
  for (let i = 0; i < items.length; i += window) {
    const batch = await Promise.all(items.slice(i, i + window).map(work));
    for (const result of batch) {
      results.push(result);
    }
  }
  return results;
}
