"""从日志库缓存并匹配注册渠道源。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Union

from .database_config import DatabaseConnectionConfig, open_database_connection
from .environment_policy import contains_removed_environment_reference
from .user import SUPPORTED_ENVIRONMENTS


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHANNEL_SOURCES_FILE = PROJECT_ROOT / "cache" / "channel_sources.json"
NEW_USER_CHANNEL_GROUP = "USH-10SC-100-group"
ORGANIC_CHANNEL_SOURCE = "Organic"


@dataclass(frozen=True)
class ChannelSource:
    """账号创建需要的渠道源参数。"""

    user_source: str
    cfg_channel_group: str
    enter_pkg: int

    @classmethod
    def from_mapping(cls, value: object) -> "ChannelSource | None":
        if not isinstance(value, dict):
            return None
        user_source = str(value.get("user_source", "")).strip()
        cfg_channel_group = str(value.get("cfg_channel_group") or "").strip()
        try:
            enter_pkg = int(value.get("enter_pkg"))
        except (TypeError, ValueError):
            return None
        if not user_source or enter_pkg not in (0, 1):
            return None
        return cls(user_source, cfg_channel_group, enter_pkg)


def load_channel_source_config(
    path: Union[str, Path] = CHANNEL_SOURCES_FILE,
) -> Dict[str, List[ChannelSource]]:
    """加载按环境隔离的渠道源缓存。"""
    config = {environment: [] for environment in SUPPORTED_ENVIRONMENTS}
    cache_path = Path(path)
    if not cache_path.exists():
        return config
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return config
    scoped = data.get("channel_sources_by_environment") if isinstance(data, dict) else None
    if not isinstance(scoped, dict):
        return config
    for environment in SUPPORTED_ENVIRONMENTS:
        values = scoped.get(environment)
        if not isinstance(values, list):
            continue
        config[environment] = [
            source
            for value in values
            if (source := ChannelSource.from_mapping(value)) is not None
            and not contains_removed_environment_reference(source.user_source)
        ]
    return config


def save_channel_sources(
    environment: str,
    sources: Iterable[ChannelSource],
    path: Union[str, Path] = CHANNEL_SOURCES_FILE,
) -> List[ChannelSource]:
    """原子保存指定环境的渠道源，不修改其他环境。"""
    if environment not in SUPPORTED_ENVIRONMENTS:
        raise ValueError(f"不支持的环境：{environment}")
    normalized = sorted(
        {
            source.user_source: source
            for source in sources
            if source.user_source.strip()
            and not contains_removed_environment_reference(source.user_source)
        }.values(),
        key=lambda source: source.user_source.casefold(),
    )
    if not normalized:
        raise ValueError("数据库中没有可用的渠道源")
    config = load_channel_source_config(path)
    config[environment] = normalized
    cache_path = Path(path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = cache_path.with_suffix(f"{cache_path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(
            {
                "channel_sources_by_environment": {
                    name: [asdict(source) for source in values]
                    for name, values in config.items()
                }
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(cache_path)
    return normalized


def log_database_name_for_environment(
    environment: str,
    connection: DatabaseConnectionConfig,
) -> str:
    """读取显式日志库配置，并兼容旧版自动推导规则。"""
    configured_name = connection.log_database_name.strip()
    if configured_name:
        return configured_name

    if environment == "huidu":
        return "ush_log_dev"

    suffix = f"_{environment}"
    log_suffix = f"_log_{environment}"
    database_name = connection.database_name.strip()
    if database_name.endswith(log_suffix):
        return database_name
    if database_name.endswith(suffix):
        return f"{database_name[:-len(suffix)]}_log{suffix}"
    return f"ush_log_{environment}"


def fetch_channel_sources(
    environment: str,
    connection: DatabaseConnectionConfig,
) -> List[ChannelSource]:
    """从对应环境的日志库读取渠道匹配参数。"""
    if environment not in SUPPORTED_ENVIRONMENTS:
        raise ValueError(f"不支持的环境：{environment}")
    log_connection = replace(
        connection,
        database_name=log_database_name_for_environment(environment, connection),
    )
    with open_database_connection(log_connection) as database:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT user_source, cfg_channel_group, enter_pkg "
                "FROM log_user_source WHERE user_source <> ''"
            )
            rows = cursor.fetchall()
    return [
        ChannelSource(
            user_source=str(row[0]).strip(),
            cfg_channel_group=str(row[1] or "").strip(),
            enter_pkg=int(row[2]),
        )
        for row in rows
        if row
        and str(row[0]).strip()
        and not contains_removed_environment_reference(row[0])
        and int(row[2]) in (0, 1)
    ]


def resolve_channel_source(
    sources: Sequence[ChannelSource],
    *,
    can_enter_b: bool,
    has_new_user_offer: bool,
    preferred_sources: Sequence[str] = (),
) -> str:
    """按 B 面和新手套路参数匹配注册接口使用的渠道源。"""
    if not can_enter_b:
        return ORGANIC_CHANNEL_SOURCE

    candidates = [
        source.user_source
        for source in sources
        if source.enter_pkg == 1
        and (
            (source.cfg_channel_group == NEW_USER_CHANNEL_GROUP)
            == has_new_user_offer
        )
    ]
    if not candidates:
        offer_label = "有" if has_new_user_offer else "无"
        raise ValueError(f"未找到可进 B 面且{offer_label}新手套路的渠道源，请更新参数")

    candidate_set = set(candidates)
    for preferred in preferred_sources:
        if preferred in candidate_set:
            return preferred

    return min(
        candidates,
        key=lambda source: (
            "test-web" in source.casefold(),
            "test_ua_custom" in source.casefold(),
            source.count("|") < 2,
            len(source),
            source.casefold(),
        ),
    )


def resolve_registration_channel(
    environment: str,
    sources: Sequence[ChannelSource],
    *,
    can_enter_b: bool,
    has_new_user_offer: bool,
    preferred_sources: Sequence[str] = (),
) -> str:
    """校验环境并自动匹配注册渠道源。"""
    if environment not in SUPPORTED_ENVIRONMENTS:
        raise ValueError(f"不支持的环境：{environment}")
    return resolve_channel_source(
        sources,
        can_enter_b=can_enter_b,
        has_new_user_offer=has_new_user_offer,
        preferred_sources=preferred_sources,
    )
