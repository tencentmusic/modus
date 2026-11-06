import java.util.concurrent.Executor;

/** 本夹具的已有 API；配置在构造时验证，不支持动态更新。 */
public final class Kit {
    public interface Store {
        /** 单条原子条件写入；false 表示未预留，不保证整批原子性。 */
        boolean tryReserve(String tenant, String id);
    }

    public static final class Limits {
        public final int window;
        public final long waitMillis;

        public Limits(int window, long waitMillis) {
            if (window <= 0 || waitMillis <= 0) {
                throw new IllegalArgumentException("positive limits required");
            }
            this.window = window;
            this.waitMillis = waitMillis;
        }
    }

    public final Executor executor;
    public final Store store;
    public final Limits limits;

    public Kit(Executor executor, Store store, Limits limits) {
        this.executor = java.util.Objects.requireNonNull(executor);
        this.store = java.util.Objects.requireNonNull(store);
        this.limits = java.util.Objects.requireNonNull(limits);
    }
}
