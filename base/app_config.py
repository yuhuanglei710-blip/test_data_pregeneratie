"""保存用户维护的应用参数。"""

import json
from pathlib import Path
from typing import Dict, Iterable, List, Union

from .user import DEFAULT_CHANNEL_CODE, SUPPORTED_ENVIRONMENTS


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHANNEL_CODES_FILE = PROJECT_ROOT / "cache" / "channel_codes.json"


def _normalize_channel_codes(values: Iterable[object]) -> List[str]:
    """清理 Channel Code，并移除空值和重复项。"""
    normalized: List[str] = []
    seen = set()
    for value in values:
        if not isinstance(value, str):
            continue
        channel_code = value.strip()
        if not channel_code or channel_code in seen:
            continue
        seen.add(channel_code)
        normalized.append(channel_code)
    return normalized


def _default_config() -> Dict[str, List[str]]:
    """为每个环境生成默认 Channel Code 列表。"""
    return {
        environment: [DEFAULT_CHANNEL_CODE]
        for environment in SUPPORTED_ENVIRONMENTS
    }


def load_channel_code_config(
    path: Union[str, Path] = CHANNEL_CODES_FILE,
) -> Dict[str, List[str]]:
    """加载按环境隔离的 Channel Code，并兼容旧配置。"""
    config = _default_config()
    config_path = Path(path)
    if not config_path.exists():
        return config

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return config

    if not isinstance(data, dict):
        return config

    scoped_values = data.get("channel_codes_by_environment")
    if isinstance(scoped_values, dict):
        for environment in SUPPORTED_ENVIRONMENTS:
            codes = _normalize_channel_codes(scoped_values.get(environment, []))
            if codes:
                config[environment] = codes
        return config

    # Legacy flat lists belonged to the previously implicit default environment.
    legacy_codes = _normalize_channel_codes(data.get("channel_codes", []))
    if legacy_codes:
        config["dev"] = legacy_codes
    return config


def load_channel_codes(
    environment: str = "dev",
    path: Union[str, Path] = CHANNEL_CODES_FILE,
) -> List[str]:
    """加载指定环境的 Channel Code。"""
    if environment not in SUPPORTED_ENVIRONMENTS:
        raise ValueError(f"不支持的环境：{environment}")
    return load_channel_code_config(path)[environment]


def _write_config(
    config: Dict[str, List[str]],
    path: Union[str, Path],
) -> None:
    """原子写入所有环境的 Channel Code。"""
    config_path = Path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = config_path.with_suffix(f"{config_path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(
            {"channel_codes_by_environment": config},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(config_path)


def save_channel_codes(
    environment: str,
    channel_codes: Iterable[str],
    path: Union[str, Path] = CHANNEL_CODES_FILE,
) -> List[str]:
    """只保存指定环境，不影响其他环境。"""
    if environment not in SUPPORTED_ENVIRONMENTS:
        raise ValueError(f"不支持的环境：{environment}")
    codes = _normalize_channel_codes(channel_codes)
    if not codes:
        raise ValueError("至少保留一个 Channel Code")

    config = load_channel_code_config(path)
    config[environment] = codes
    _write_config(config, path)
    return codes
