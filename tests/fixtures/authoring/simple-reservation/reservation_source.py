"""会议室预约教学项目：同步方法、单实例内存数据，不提供生产保障。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime


class ReservationError(ValueError):
    """调用方按稳定 code 处理可预期的业务拒绝。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Room:
    room_id: str
    name: str
    capacity: int


@dataclass(frozen=True)
class Reservation:
    reservation_id: str
    room_id: str
    organizer: str
    attendee_count: int
    start_at: datetime
    end_at: datetime
    status: str = "confirmed"
    cancel_reason: str | None = None


class ReservationService:
    """只支持顺序调用；校验与写入之间没有锁或跨进程事务。"""

    def __init__(self) -> None:
        self._rooms = {
            "A201": Room("A201", "梧桐会议室", 6),
            "B105": Room("B105", "银杏会议室", 12),
        }
        self._reservations: dict[str, Reservation] = {}
        self._next_id = 1

    def create_reservation(
        self,
        *,
        room_id: str,
        organizer: str,
        attendee_count: int,
        start_at: datetime,
        end_at: datetime,
    ) -> Reservation:
        """检查区间后写入内存并返回快照。

        教学约定人数包含组织者；实现只校验数字，不核实参会名单。
        """
        room_id = self._text(room_id, "room_id", 40)
        room = self._rooms.get(room_id)
        if room is None:
            raise ReservationError("room_not_found", "会议室不存在")
        organizer = self._text(organizer, "organizer", 80)
        if type(attendee_count) is not int or attendee_count < 1:
            raise ReservationError("invalid_attendee_count", "参会人数必须是正整数")
        if attendee_count > room.capacity:
            raise ReservationError("capacity_exceeded", "参会人数超过会议室容量")
        start_at = self._utc(start_at, "start_at")
        end_at = self._utc(end_at, "end_at")
        if start_at >= end_at:
            raise ReservationError("invalid_interval", "结束时间必须晚于开始时间")
        for current in self._reservations.values():
            if (
                current.room_id == room_id
                and current.status == "confirmed"
                and start_at < current.end_at
                and current.start_at < end_at
            ):
                raise ReservationError("room_unavailable", "该会议室的时间区间已被占用")
        reservation = Reservation(
            reservation_id=f"RES-{self._next_id:04d}",
            room_id=room_id,
            organizer=organizer,
            attendee_count=attendee_count,
            start_at=start_at,
            end_at=end_at,
        )
        self._reservations[reservation.reservation_id] = reservation
        self._next_id += 1
        return reservation

    def cancel_reservation(self, *, reservation_id: str, reason: str) -> Reservation:
        """保留预约记录并释放时段；有效的重复取消保留第一次原因。"""
        reservation_id = self._text(reservation_id, "reservation_id", 40)
        current = self._reservations.get(reservation_id)
        if current is None:
            raise ReservationError("reservation_not_found", "预约记录不存在")
        reason = self._text(reason, "reason", 200)
        if current.status == "cancelled":
            return current
        cancelled = replace(current, status="cancelled", cancel_reason=reason)
        self._reservations[reservation_id] = cancelled
        return cancelled

    @staticmethod
    def _text(value: str, field: str, max_length: int) -> str:
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > max_length:
            raise ReservationError(f"invalid_{field}", f"{field} 必须为非空且未超长的文本")
        return value.strip()

    @staticmethod
    def _utc(value: datetime, field: str) -> datetime:
        if not isinstance(value, datetime) or value.utcoffset() is None:
            raise ReservationError(f"invalid_{field}", f"{field} 必须包含时区")
        return value.astimezone(UTC)


def run_demo() -> None:
    """固定示例日期，不依赖当前时钟；这些断言用于样稿的本地自验。"""
    service = ReservationService()
    at = datetime.fromisoformat
    start = at("2026-11-05T09:00:00+08:00")
    end = at("2026-11-05T10:00:00+08:00")

    def create(
        *,
        room_id: str = "A201",
        organizer: str = "林青",
        attendee_count: int = 4,
        start_at: datetime = start,
        end_at: datetime = end,
    ) -> Reservation:
        return service.create_reservation(
            room_id=room_id,
            organizer=organizer,
            attendee_count=attendee_count,
            start_at=start_at,
            end_at=end_at,
        )

    def rejected(code: str, action: Callable[[], object]) -> None:
        try:
            action()
        except ReservationError as error:
            assert error.code == code, (error.code, code)
        else:
            raise AssertionError(f"预期 {code}，调用却成功")

    first = create()
    assert first.reservation_id == "RES-0001" and first.status == "confirmed"
    assert first.start_at.isoformat() == "2026-11-05T01:00:00+00:00"
    rejected("room_unavailable", lambda: create(start_at=at("2026-11-05T09:30:00+08:00")))
    adjacent = create(start_at=end, end_at=at("2026-11-05T11:00:00+08:00"))
    assert adjacent.reservation_id == "RES-0002"
    assert create(room_id="B105").reservation_id == "RES-0003"
    cancelled = service.cancel_reservation(reservation_id=first.reservation_id, reason="会议改期")
    assert cancelled.status == "cancelled" and cancelled.cancel_reason == "会议改期"
    again = service.cancel_reservation(reservation_id=first.reservation_id, reason="再次取消")
    assert again is cancelled and first.status == "confirmed"
    assert create().reservation_id == "RES-0004"
    rejected("capacity_exceeded", lambda: create(attendee_count=7))
    rejected("invalid_attendee_count", lambda: create(attendee_count=True))
    rejected("room_not_found", lambda: create(room_id="C999"))
    rejected("invalid_start_at", lambda: create(start_at=datetime(2026, 11, 5, 9)))
    rejected("invalid_interval", lambda: create(end_at=start))
    rejected("invalid_organizer", lambda: create(organizer="  "))
    rejected(
        "invalid_reason",
        lambda: service.cancel_reservation(reservation_id=first.reservation_id, reason=" "),
    )
    rejected(
        "reservation_not_found",
        lambda: service.cancel_reservation(reservation_id="RES-9999", reason="改期"),
    )
    assert service._next_id == 5 and len(service._reservations) == 4
    print(
        "教学自验通过：创建、UTC 归一、冲突拒绝、相邻时段、不同会议室、取消、重复取消、释放重订和输入拒绝。"
    )


if __name__ == "__main__":
    run_demo()
