import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

public final class ReserveBatchCheck {
    private interface Action {
        void run() throws Exception;
    }

    private static <T extends Throwable> T expect(Class<T> type, Action action) throws Exception {
        try {
            action.run();
        } catch (Throwable error) {
            if (type.isInstance(error)) {
                return type.cast(error);
            }
            throw new AssertionError("expected " + type.getSimpleName(), error);
        }
        throw new AssertionError("expected " + type.getSimpleName());
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static void preservesOrderAndValidatesBeforeWriting() throws Exception {
        List<String> calls = new ArrayList<>();
        Kit kit = new Kit(Runnable::run, (tenant, id) -> {
            calls.add(tenant + ":" + id);
            return true;
        }, new Kit.Limits(2, 1000));
        List<String> input = Arrays.asList("b", "a", "b");
        check(ReserveBatch.reserve(kit, "t", input).equals(Arrays.asList("b", "a")), "order");
        check(input.equals(Arrays.asList("b", "a", "b")), "input changed");
        check(calls.equals(Arrays.asList("t:b", "t:a")), "existing store not reused");

        calls.clear();
        check(ReserveBatch.reserve(kit, "t", Collections.emptyList()).isEmpty(), "empty batch");
        expect(IllegalArgumentException.class, () -> ReserveBatch.reserve(kit, "t", null));
        expect(IllegalArgumentException.class,
                () -> ReserveBatch.reserve(kit, "t", Arrays.asList("a", null)));
        expect(IllegalArgumentException.class,
                () -> ReserveBatch.reserve(kit, "t", Arrays.asList("a", "")));
        expect(IllegalArgumentException.class,
                () -> ReserveBatch.reserve(kit, "", Arrays.asList("a")));
        check(calls.isEmpty(), "side effect before validation");
        expect(IllegalArgumentException.class, () -> new Kit.Limits(0, 1));
        expect(IllegalArgumentException.class, () -> new Kit.Limits(1, 0));
    }

    private static void propagatesStoreFailures() throws Exception {
        Kit.Limits limits = new Kit.Limits(2, 1000);
        expect(IllegalStateException.class, () -> ReserveBatch.reserve(
                new Kit(Runnable::run, (tenant, id) -> false, limits), "t", Arrays.asList("a")));
        IllegalArgumentException cause = new IllegalArgumentException("store failure");
        ExecutionException failure = expect(ExecutionException.class, () -> ReserveBatch.reserve(
                new Kit(Runnable::run, (tenant, id) -> { throw cause; }, limits),
                "t", Arrays.asList("a")));
        check(failure.getCause() == cause, "store failure cause lost");
    }

    private static void rejectionPreservesAcceptedWrites() throws Exception {
        List<String> calls = new ArrayList<>();
        AtomicInteger submitted = new AtomicInteger();
        Executor executor = task -> {
            if (submitted.incrementAndGet() == 2) {
                throw new RejectedExecutionException("executor saturated");
            }
            task.run();
        };
        Kit kit = new Kit(executor, (tenant, id) -> {
            calls.add(id);
            return true;
        }, new Kit.Limits(2, 1000));
        expect(RejectedExecutionException.class,
                () -> ReserveBatch.reserve(kit, "t", Arrays.asList("a", "b", "c")));
        check(calls.equals(Arrays.asList("a")), "accepted write must survive rejection");
        check(submitted.get() == 2, "submission continued after rejection");
    }

    private static void timeoutAndInterruptionDoNotRunQueuedWrites() throws Exception {
        // 保留任务但不执行，确定性地模拟队列等待；不依赖 sleep 或真实负载。
        List<Runnable> queued = new ArrayList<>();
        List<String> calls = new ArrayList<>();
        Kit.Store store = (tenant, id) -> {
            calls.add(id);
            return true;
        };
        expect(TimeoutException.class, () -> ReserveBatch.reserve(
                new Kit(queued::add, store, new Kit.Limits(1, 10)), "t", Arrays.asList("a")));
        Thread.currentThread().interrupt();
        try {
            expect(InterruptedException.class, () -> ReserveBatch.reserve(
                    new Kit(queued::add, store, new Kit.Limits(1, 1000)), "t", Arrays.asList("b")));
            check(Thread.currentThread().isInterrupted(), "interrupt lost");
        } finally {
            Thread.interrupted();
        }
        // 此处只检查尚未开始的 CompletableFuture；运行中的外部写入仍可能完成。
        for (Runnable task : queued) {
            task.run();
        }
        check(calls.isEmpty(), "cancelled queued task wrote to store");
    }

    private static void boundsAdmissionAndPreservesSharedExecutor() throws Exception {
        ExecutorService shared = Executors.newFixedThreadPool(4);
        CountDownLatch firstWindow = new CountDownLatch(2);
        AtomicInteger inFlight = new AtomicInteger();
        AtomicInteger peak = new AtomicInteger();
        Executor tracked = task -> {
            int accepted = inFlight.incrementAndGet();
            peak.accumulateAndGet(accepted, Math::max);
            shared.execute(task);
        };
        Kit.Store store = (tenant, id) -> {
            firstWindow.countDown();
            try {
                check(firstWindow.await(5, TimeUnit.SECONDS), "first window did not overlap");
                return true;
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("store interrupted", error);
            } finally {
                inFlight.decrementAndGet();
            }
        };
        try {
            List<String> ids = Arrays.asList("a", "b", "c", "d", "e");
            check(ReserveBatch.reserve(new Kit(tracked, store, new Kit.Limits(2, 10000)), "t", ids)
                    .equals(ids), "concurrent result order");
            check(peak.get() == 2, "window did not bound accepted work");
            check(inFlight.get() == 0, "unobserved work remains");
            check(shared.submit(() -> true).get(5, TimeUnit.SECONDS), "shared executor closed");
        } finally {
            // 只有测试宿主拥有共享池，reserve 不承担关闭责任。
            shared.shutdownNow();
            check(shared.awaitTermination(5, TimeUnit.SECONDS), "executor did not terminate");
        }
    }

    public static void main(String[] args) throws Exception {
        preservesOrderAndValidatesBeforeWriting();
        propagatesStoreFailures();
        rejectionPreservesAcceptedWrites();
        timeoutAndInterruptionDoNotRunQueuedWrites();
        boundsAdmissionAndPreservesSharedExecutor();
        System.out.println("Java behavior checks passed");
    }
}
