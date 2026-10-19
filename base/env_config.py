"""从项目根目录 ``env.json`` 读取应用配置。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping, Union


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_CONFIG_FILE = PROJECT_ROOT / "env.json"


def load_env_config(
    project_root: Union[str, Path] = PROJECT_ROOT,
) -> Dict[str, Any]:
    """读取并校验根配置；配置错误时直接给出可定位的异常。"""
    config_file = Path(project_root) / "env.json"
    try:
        content = config_file.read_text(encoding="utf-8")
    except OSError as error:
        raise RuntimeError(f"无法读取配置文件 {config_file}: {error}") from error

    try:
        config = json.loads(content)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"配置文件 {config_file} 不是有效 JSON: {error}"
        ) from error
    if not isinstance(config, dict):
        raise RuntimeError(f"配置文件 {config_file} 的根节点必须是 JSON 对象")
    return config


def config_section(
    name: str,
    project_root: Union[str, Path] = PROJECT_ROOT,
) -> Mapping[str, Any]:
    """读取一个必需的对象配置段。"""
    section = load_env_config(project_root).get(name)
    if not isinstance(section, dict):
        raise RuntimeError(f"env.json 缺少对象配置段 {name!r}")
    return section


def environment_config(
    environment: str,
    project_root: Union[str, Path] = PROJECT_ROOT,
) -> Mapping[str, Any]:
    """读取指定运行环境的配置。"""
    environments = config_section("environment", project_root)
    config = environments.get(environment)
    if not isinstance(config, dict):
        supported = "、".join(str(name) for name in environments)
        raise ValueError(
            f"环境 {environment!r} 未在 env.json 中配置，可选值：{supported}"
        )
    return config


def required_string(
    config: Mapping[str, Any],
    key: str,
    *,
    context: str,
) -> str:
    """读取必需的非空字符串配置。"""
    value = config.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"env.json 的 {context}.{key} 必须是非空字符串")
    return value.strip()
