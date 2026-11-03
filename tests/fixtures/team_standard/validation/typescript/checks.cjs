const assert = require("node:assert/strict");
const path = require("node:path");

const root = process.argv[2];
const { createLookup } = require(path.join(root, "browser/solution/browser.js"));
const { reserve } = require(path.join(root, "worker/solution/worker.js"));
const { mapWindow } = require(path.join(root, "worker/ports.js"));

function lookupHarness() {
  const requests = new Map();
  const views = [];
  const client = {
    lookup(id, signal) {
      return new Promise((resolve, reject) => {
        requests.set(id, { resolve, reject, signal });
      });
    },
  };
  return { requests, views, lookup: createLookup(client, view => views.push(view)) };
}

async function staleRequestsCannotPublish() {
  // 即使客户端忽略 abort，旧成功和旧失败都不能替换最新结果。
  for (const staleOutcome of ["resolve", "reject"]) {
    const { requests, views, lookup } = lookupHarness();
    const old = lookup.load("old");
    const latest = lookup.load("latest");
    assert.equal(requests.get("old").signal.aborted, true);
    requests.get("latest").resolve("new value");
    await latest;
    requests.get("old")[staleOutcome](
      staleOutcome === "resolve" ? "stale value" : new Error("stale failure"),
    );
    await old;
    assert.deepEqual(views, [{ kind: "ready", value: "new value" }]);
  }
}

async function failuresAndStopPreserveTheViewContract() {
  const { requests, views, lookup } = lookupHarness();
  await assert.rejects(lookup.load(""), /id required/);
  assert.equal(requests.size, 0);

  const failed = lookup.load("failure");
  const error = new Error("offline");
  requests.get("failure").reject(error);
  await failed;
  assert.deepEqual(views, [{ kind: "failed", error }]);

  const late = lookup.load("stopped");
  lookup.stop();
  lookup.stop();
  assert.equal(requests.get("stopped").signal.aborted, true);
  requests.get("stopped").resolve("ignored");
  await late;
  await assert.rejects(lookup.load("after-stop"), /lookup stopped/);
  assert.equal(requests.has("after-stop"), false);
  assert.deepEqual(views, [{ kind: "failed", error }]);
}

function workerHarness() {
  const observed = { policyReads: 0, active: 0, peak: 0, scheduled: 0, writes: [] };
  const ports = {
    readPolicy() {
      observed.policyReads++;
      return { window: 2 };
    },
    async updateIfPending(tenant, id) {
      observed.active++;
      observed.peak = Math.max(observed.peak, observed.active);
      try {
        await Promise.resolve();
        observed.writes.push([tenant, id]);
        return true;
      } finally {
        observed.active--;
      }
    },
    mapWindow(...args) {
      observed.scheduled++;
      return mapWindow(...args);
    },
  };
  return { ports, observed };
}

async function workerReusesBoundedSchedulingAndOneSnapshot() {
  const { ports, observed } = workerHarness();
  assert.deepEqual(await reserve(ports, "tenant", ["b", "a", "b", "c"]), ["b", "a", "c"]);
  assert.equal(observed.policyReads, 1);
  assert.equal(observed.scheduled, 1);
  assert.equal(observed.peak, 2);
  assert.deepEqual(observed.writes, [["tenant", "b"], ["tenant", "a"], ["tenant", "c"]]);
}

async function workerRejectsInvalidInputBeforeScheduling() {
  const { ports, observed } = workerHarness();
  for (const ids of [["valid", ""], ["valid", null], Array(2)]) {
    await assert.rejects(reserve(ports, "tenant", ids), /id required/);
  }
  await assert.rejects(reserve(ports, "", ["valid"]), /tenant required/);
  assert.equal(observed.policyReads, 0);
  for (const window of [0, -1, 1.5, NaN, Infinity]) {
    await assert.rejects(
      reserve({ ...ports, readPolicy: () => ({ window }) }, "tenant", ["valid"]),
      /invalid window/,
    );
  }
  assert.equal(observed.scheduled, 0);
  assert.deepEqual(observed.writes, []);
}

async function workerPropagatesFailuresWithoutClaimingRollback() {
  const { ports, observed } = workerHarness();
  await assert.rejects(reserve({ ...ports, updateIfPending: async () => false }, "t", ["x"]),
    /reservation conflict/);
  const failure = new Error("dependency unavailable");
  for (const failingPort of ["readPolicy", "mapWindow", "updateIfPending"]) {
    await assert.rejects(
      reserve({ ...ports, [failingPort]: () => { throw failure; } }, "t", ["x"]),
      error => error === failure,
    );
  }

  // 同窗口的已接收任务可以继续完成，但失败后不能提交下一窗口。
  await assert.rejects(reserve({
    ...ports,
    async updateIfPending(tenant, id) {
      if (id === "conflict") return false;
      return ports.updateIfPending(tenant, id);
    },
  }, "tenant", ["accepted", "conflict", "not-submitted"]), /reservation conflict/);
  assert.deepEqual(observed.writes, [["tenant", "accepted"]]);
}

async function main() {
  await staleRequestsCannotPublish();
  await failuresAndStopPreserveTheViewContract();
  await workerReusesBoundedSchedulingAndOneSnapshot();
  await workerRejectsInvalidInputBeforeScheduling();
  await workerPropagatesFailuresWithoutClaimingRollback();
  console.log("TypeScript behavior checks passed");
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
