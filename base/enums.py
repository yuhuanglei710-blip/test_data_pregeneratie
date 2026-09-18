"""接口工具共用的枚举。"""

from enum import Enum


class Platform(Enum):
    """支持的账号注册平台。"""

    web = 1
    android = 2
    ios = 3


class ComplianceStatus(Enum):
    """KYC 合规状态。"""

    compliance = 1
    noncompliance = 0


# Keep the original misspelled name so existing imports continue to work.
Compliancestatus = ComplianceStatus


class ChannelCode(Enum):
    """预留的 Channel Code 枚举。"""


class TimestampMethod(Enum):
    """时间戳调整方向。"""

    add = 1
    sub = 0
