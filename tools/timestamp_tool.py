"""时间戳计算工具。"""

import time
from typing import Optional


SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 60 * SECONDS_PER_MINUTE
SECONDS_PER_DAY = 24 * SECONDS_PER_HOUR


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
