"""从项目根目录 ``env.json`` 加载通用工具的本地路径配置。"""

from __future__ import annotations

import os
from pathlib import Path

from .env_config import config_section


PROJECT_ROOT = Path(__file__).resolve().parent.parent
_LOCAL_CONFIG = config_section("local")


def env_value(name: str, default: str = "") -> str:
    """优先读取进程环境，其次读取根目录 ``env.json``。"""
    process_value = os.environ.get(name)
    if process_value is not None:
        return process_value.strip()
    value = _LOCAL_CONFIG.get(name, default)
    return str(value if value is not None else default).strip()


def configured_path(name: str, default: str) -> Path:
    """读取路径配置；相对路径以项目根目录为基准。"""
    value = Path(env_value(name, default)).expanduser()
    return value if value.is_absolute() else PROJECT_ROOT / value


TOOL_DATA_DIR = configured_path("TOOL_DATA_DIR", "cache")
QUICK_ACCESS_FILE = configured_path(
    "QUICK_ACCESS_FILE",
    str(TOOL_DATA_DIR / "quick_access.json"),
)
SSH_HOSTS_FILE = configured_path(
    "SSH_HOSTS_FILE",
    str(TOOL_DATA_DIR / "ssh_hosts.json"),
)
SSH_PRIVATE_KEYS_FILE = configured_path(
    "SSH_PRIVATE_KEYS_FILE",
    str(TOOL_DATA_DIR / "ssh_private_keys.json"),
)
SSH_PRIVATE_KEY_DIR = configured_path(
    "SSH_PRIVATE_KEY_DIR",
    str(TOOL_DATA_DIR / "ssh_keys"),
)
