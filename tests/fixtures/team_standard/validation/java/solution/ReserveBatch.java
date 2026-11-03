import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public final class ReserveBatch {
    public static List<String> reserve(Kit kit, String tenant, List<String> ids)
            throws InterruptedException, ExecutionException, TimeoutException {
        if (tenant == null || tenant.isEmpty() || ids == null) {
            throw new IllegalArgumentException("tenant and ids required");
        }
        LinkedHashSet<String> unique = new LinkedHashSet<>();
        for (String id : ids) {
            if (id == null || id.isEmpty()) {
                throw new IllegalArgumentException("id required");
            }
            unique.add(id);
        }
        List<String> ordered = new ArrayList<>(unique);
        Kit.Limits limits = kit.limits;
        long started = System.nanoTime();
        long budget = TimeUnit.MILLISECONDS.toNanos(limits.waitMillis);
        for (int start = 0; start < ordered.size();) {
            int end = start + Math.min(limits.window, ordered.size() - start);
            List<CompletableFuture<Boolean>> pending = new ArrayList<>();
            try {
                for (int i = start; i < end; i++) {
                    remaining(started, budget);
                    String id = ordered.get(i);
                    pending.add(CompletableFuture.supplyAsync(
                            () -> kit.store.tryReserve(tenant, id), kit.executor));
                }
                for (CompletableFuture<Boolean> future : pending) {
                    if (!future.get(remaining(started, budget), TimeUnit.NANOSECONDS)) {
                        throw new IllegalStateException("reservation conflict");
                    }
                }
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                throw error;
            } finally {
                // 仅结束等待状态，不承诺中断执行或撤销已经完成的写入。
                for (CompletableFuture<Boolean> future : pending) {
                    if (!future.isDone()) {
                        future.cancel(false);
                    }
                }
            }
            start = end;
        }
        return ordered;
    }

    private static long remaining(long started, long budget) throws TimeoutException {
        long value = budget - (System.nanoTime() - started);
        if (value <= 0) {
            throw new TimeoutException("batch deadline exceeded");
        }
        return value;
    }
}
