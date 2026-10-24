"""单进程、显式调度的联系人导入教学夹具。

记录、幂等键和队列都保存在内存；没有生产队列或持久任务系统。
直接运行本文件可以复核正反例，不能据此推断真实进程崩溃恢复能力。
"""

import json
import re
from collections import deque
from copy import deepcopy
from hashlib import sha256

MAX_ROWS = 100
MAX_ATTEMPTS = 2
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ImportErrorBase(Exception):
    """区分教学业务错误，避免将任意程序异常都称为可恢复故障。"""


class InvalidRequest(ImportErrorBase):
    pass


class IdempotencyConflict(ImportErrorBase):
    pass


class JobNotFound(ImportErrorBase):
    pass


class RetryNotAllowed(ImportErrorBase):
    pass


class StorageUnavailable(ImportErrorBase):
    """仅在行处理前注入，不模拟联系人已写而进度未保存的故障。"""


class ContactImporter:
    """四个公开入口；租户由调用方提供，不承担真实身份认证。"""

    def __init__(self):
        self._jobs = {}
        self._keys = {}
        self._contacts = {}
        self._queue: deque[str] = deque()

    def submit(self, tenant_id, idempotency_key, rows):
        """结构正确只表示可以受理，行校验和联系人写入留到执行阶段。"""
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise InvalidRequest("tenant_id 必须为非空白字符串")
        if not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 64:
            raise InvalidRequest("idempotency_key 长度必须为 1–64")
        if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ROWS:
            raise InvalidRequest(f"rows 必须包含 1–{MAX_ROWS} 行")
        if any(
            not isinstance(row, dict)
            or set(row) != {"name", "email"}
            or not all(isinstance(value, str) for value in row.values())
            for row in rows
        ):
            raise InvalidRequest("每行必须恰好包含字符串 name 和 email")
        fingerprint = sha256(
            json.dumps(rows, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest()
        key = (tenant_id, idempotency_key)
        if key in self._keys:
            job = self._jobs[self._keys[key]]
            if job["fingerprint"] != fingerprint:
                raise IdempotencyConflict("同一幂等键已经绑定不同输入")
            return self._view(job)
        job_id = f"import-{len(self._jobs) + 1}"
        job = {
            "job_id": job_id,
            "tenant_id": tenant_id,
            "idempotency_key": idempotency_key,
            "fingerprint": fingerprint,
            "rows": deepcopy(rows),
            "status": "queued",
            "attempts": 0,
            "results": [],
            "error": None,
            "retryable": False,
        }
        self._jobs[job_id] = job
        self._keys[key] = job_id
        self._queue.append(job_id)
        return self._view(job)

    def query(self, tenant_id, job_id):
        """返回独立快照；查询不能替代显式执行。"""
        return self._view(self._find(tenant_id, job_id))

    def run_next(self, *, fail_before_row=None):
        """同步处理队首任务，可指定行前故障以检查保留和恢复边界。

        fail_before_row 使用从零开始的绝对输入行号，仅用于教学控制，
        不表示真实外部服务故障或可对外发布的生产接口。
        """
        if fail_before_row is not None and (
            type(fail_before_row) is not int or fail_before_row < 0
        ):
            raise InvalidRequest("fail_before_row 必须为非负整数")
        if not self._queue:
            return None
        job = self._jobs[self._queue.popleft()]
        job["status"] = "running"
        job["attempts"] += 1
        job["retryable"] = False
        try:
            for index in range(len(job["results"]), len(job["rows"])):
                if index == fail_before_row:
                    raise StorageUnavailable("在行处理前注入模拟存储故障")
                row = job["rows"][index]
                name, email = row["name"].strip(), row["email"].strip().lower()
                reason = (
                    "empty_name"
                    if not name
                    else ("invalid_email" if not EMAIL.fullmatch(email) else None)
                )
                if reason:
                    result = {
                        "row_index": index,
                        "email": email,
                        "outcome": "rejected",
                        "reason": reason,
                    }
                else:
                    key = (job["tenant_id"], email)
                    outcome = "updated" if key in self._contacts else "created"
                    self._contacts[key] = {
                        "tenant_id": job["tenant_id"],
                        "email": email,
                        "name": name,
                    }
                    result = {
                        "row_index": index,
                        "email": email,
                        "outcome": outcome,
                        "reason": None,
                    }
                job["results"].append(result)
            rejected = sum(item["outcome"] == "rejected" for item in job["results"])
            job["status"] = (
                "succeeded"
                if rejected == 0
                else "failed"
                if rejected == len(job["rows"])
                else "partial"
            )
            job["error"] = "all_rows_rejected" if job["status"] == "failed" else None
        except StorageUnavailable:
            job["status"] = "failed"
            job["error"] = "storage_unavailable"
            job["retryable"] = job["attempts"] < MAX_ATTEMPTS
        return self._view(job)

    def retry(self, tenant_id, job_id):
        """恢复只重新排队并保留已有结果，不在本次调用继续执行。"""
        job = self._find(tenant_id, job_id)
        if job["status"] != "failed" or not job["retryable"]:
            raise RetryNotAllowed("仅允许可重试的存储故障任务重新排队")
        job["status"], job["error"], job["retryable"] = "queued", None, False
        self._queue.append(job_id)
        return self._view(job)

    def _find(self, tenant_id, job_id):
        job = self._jobs.get(job_id)
        if job is None or job["tenant_id"] != tenant_id:
            raise JobNotFound("当前租户中不存在该任务")
        return job

    @staticmethod
    def _view(job):
        results = job["results"]
        return deepcopy(
            {
                "job_id": job["job_id"],
                "status": job["status"],
                "total": len(job["rows"]),
                "processed": len(results),
                "written": sum(r["outcome"] != "rejected" for r in results),
                "rejected": sum(r["outcome"] == "rejected" for r in results),
                "attempts": job["attempts"],
                "retryable": job["retryable"],
                "error": job["error"],
                "results": results,
            }
        )


def demonstrate():
    """以确定性示例复核正反例、部分成功、幂等和有条件恢复。"""
    system = ContactImporter()
    rows = [
        {"name": "林禾", "email": "LIN@example.test"},
        {"name": "周宁", "email": "bad-address"},
        {"name": "林禾（更新）", "email": "lin@example.test"},
    ]
    accepted = system.submit("team-a", "batch-a", rows)
    job_id = accepted["job_id"]
    assert accepted["status"] == "queued" and accepted["processed"] == 0
    assert system.submit("team-a", "batch-a", rows) == accepted
    final = system.run_next()
    assert (final["status"], final["written"], final["rejected"]) == ("partial", 2, 1)
    assert [r["outcome"] for r in final["results"]] == ["created", "rejected", "updated"]
    assert len(system._contacts) == 1  # 两次写入不等于两个独立联系人。
    assert system.submit("team-a", "batch-a", rows) == final
    assert system.run_next() is None  # 重复提交没有产生额外待执行任务。
    errors = []
    for operation, expected in [
        (lambda: system.submit("team-a", "batch-a", rows[:1]), IdempotencyConflict),
        (lambda: system.submit("team-a", "empty", []), InvalidRequest),
        (lambda: system.query("team-b", job_id), JobNotFound),
        (lambda: system.retry("team-a", job_id), RetryNotAllowed),
    ]:
        try:
            operation()
        except expected:
            errors.append(expected.__name__)
        else:
            raise AssertionError(f"预期异常 {expected.__name__}")
    recovery_rows = [
        {"name": "陈青", "email": "chen@example.test"},
        {"name": "许白", "email": "xu@example.test"},
    ]
    recovery = system.submit("team-a", "batch-b", recovery_rows)
    failed = system.run_next(fail_before_row=1)
    assert (failed["processed"], failed["retryable"], failed["attempts"]) == (1, True, 1)
    requeued = system.retry("team-a", recovery["job_id"])
    assert requeued["processed"] == 1 and requeued["status"] == "queued"
    recovered = system.run_next()
    assert recovered["status"] == "succeeded" and recovered["attempts"] == 2
    assert [r["outcome"] for r in recovered["results"]] == ["created", "created"]
    exhausted = system.submit("team-a", "batch-c", recovery_rows)
    system.run_next(fail_before_row=0)
    system.retry("team-a", exhausted["job_id"])
    exhausted = system.run_next(fail_before_row=0)
    assert exhausted["status"] == "failed" and not exhausted["retryable"]
    invalid = system.submit("team-a", "batch-d", [{"name": "", "email": "x"}])
    invalid = system.run_next()
    assert invalid["error"] == "all_rows_rejected" and not invalid["retryable"]
    return {
        "accepted": accepted,
        "partial": final,
        "business_errors": errors,
        "failed_before_recovery": failed,
        "recovered": recovered,
        "retry_exhausted": exhausted,
        "all_rows_rejected": invalid,
    }


if __name__ == "__main__":
    print(json.dumps(demonstrate(), ensure_ascii=False, indent=2))
