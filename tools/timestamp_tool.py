"""时间戳解析、展示与偏移计算工具。"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Union


SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 60 * SECONDS_PER_MINUTE
SECONDS_PER_DAY = 24 * SECONDS_PER_HOUR


@dataclass(frozen=True)
class TimestampResult:
    """一个时间点的常用展示格式。"""

    epoch_seconds: int
    epoch_milliseconds: int
    local_time: str
    utc_time: str
    utc_plus_8: str
    utc_minus_8: str
    iso_8601: str
    relative: str


def _format_in_zone(value: datetime, offset_hours: int) -> str:
    target = value.astimezone(timezone(timedelta(hours=offset_hours)))
    sign = "+" if offset_hours >= 0 else ""
    return f"{target:%Y-%m-%d %H:%M:%S} (UTC{sign}{offset_hours})"


def _relative_text(value: datetime, now: datetime) -> str:
    diff = value.timestamp() - now.timestamp()
    absolute = abs(diff)
    suffix = "后" if diff > 0 else "前"
    if absolute < 10:
        return "刚刚"
    if absolute < 60:
        return f"{int(absolute)}秒{suffix}"
    if absolute < 3600:
        return f"{int(absolute // 60)}分钟{suffix}"
    if absolute < 86400:
        return f"{int(absolute // 3600)}小时{suffix}"
    if absolute < 30 * 86400:
        return f"{int(absolute // 86400)}天{suffix}"
    return "未来" if diff > 0 else "很久以前"


def parse_timestamp(
    value: Union[str, int, float],
    *,
    now: Optional[datetime] = None,
) -> TimestampResult:
    """解析秒/毫秒 Unix 时间戳或常用日期时间字符串。"""
    text = str(value).strip()
    if not text:
        raise ValueError("请输入时间戳或日期时间")
    try:
        if text.lstrip("+-").isdigit():
            numeric = int(text)
            digit_count = len(text.lstrip("+-"))
            seconds = numeric / 1000 if digit_count > 10 else numeric
            parsed = datetime.fromtimestamp(seconds).astimezone()
        else:
            normalized = text.replace("Z", "+00:00") if text.endswith("Z") else text
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                parsed = parsed.astimezone()
            else:
                parsed = parsed.astimezone()
    except (OverflowError, OSError, ValueError) as error:
        raise ValueError("无法识别该时间，请输入秒/毫秒时间戳或日期时间") from error
    reference = now or datetime.now().astimezone()
    if reference.tzinfo is None:
        reference = reference.astimezone()
    epoch_milliseconds = int(parsed.timestamp() * 1000)
    utc_value = parsed.astimezone(timezone.utc)
    return TimestampResult(
        epoch_seconds=epoch_milliseconds // 1000,
        epoch_milliseconds=epoch_milliseconds,
        local_time=parsed.strftime("%Y-%m-%d %H:%M:%S"),
        utc_time=utc_value.strftime("%a, %d %b %Y %H:%M:%S GMT"),
        utc_plus_8=_format_in_zone(parsed, 8),
        utc_minus_8=_format_in_zone(parsed, -8),
        iso_8601=utc_value.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        relative=_relative_text(parsed, reference),
    )


def offset_timestamp(value: Union[str, int, float], hours: int) -> TimestampResult:
    """将输入时间偏移指定小时后重新格式化。"""
    parsed = parse_timestamp(value)
    return parse_timestamp(parsed.epoch_milliseconds + int(hours) * 3_600_000)


class TimestampTool:
    """生成和调整 Unix 时间戳。"""

    @staticmethod
    def get_timestamp() -> int:
        """返回当前秒级 Unix 时间戳。"""
        return int(time.time())

    @staticmethod
    def modify_timestamp(
        timestamp: Optional[int] = None,
        days: int = 0,
        hours: int = 0,
        minutes: int = 0,
        seconds: int = 0,
        method: int = 1,
    ) -> int:
        """method 为 1 时增加时间，否则减少时间。"""
        base_timestamp = (
            TimestampTool.get_timestamp() if timestamp is None else timestamp
        )
        total_seconds = (
            days * SECONDS_PER_DAY
            + hours * SECONDS_PER_HOUR
            + minutes * SECONDS_PER_MINUTE
            + seconds
        )
        direction = 1 if method == 1 else -1
        return base_timestamp + direction * total_seconds


if __name__ == "__main__":
    print("当前时间戳:", TimestampTool.get_timestamp())
