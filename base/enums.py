"""接口工具共用的枚举。"""

from enum import Enum

try:  # Support package and direct script imports.
    from .env_config import config_section
except ImportError:  # pragma: no cover - compatibility for direct execution.
    from env_config import config_section


_PLATFORM_CONFIG = config_section("platform")


class Platform(Enum):
    """支持的账号注册平台。"""

    web = int(_PLATFORM_CONFIG["web"])
    android = int(_PLATFORM_CONFIG["android"])
    ios = int(_PLATFORM_CONFIG["ios"])


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
