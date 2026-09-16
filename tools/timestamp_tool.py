"""Timestamp calculation utilities."""

import time
from typing import Optional


SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 60 * SECONDS_PER_MINUTE
SECONDS_PER_DAY = 24 * SECONDS_PER_HOUR


class TimestampTool:
    """Generate and adjust Unix timestamps."""

    @staticmethod
    def get_timestamp() -> int:
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
        """Add a duration when ``method`` is 1; otherwise subtract it."""
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
