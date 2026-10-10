"""已移除环境的硬性隔离策略。"""

from __future__ import annotations

from urllib.parse import urlparse


REMOVED_ENVIRONMENTS = frozenset({"prod"})
FORBIDDEN_PRODUCTION_HOSTS = frozenset(
    {
        "api.hotspin777.com",
        "admin.hotspin777.com",
        "web.hotspin777.com",
        "prodweb.hotspin777.com",
        "www.hotspin777.com",
        "hotspin777.com",
    }
)


def contains_removed_environment_reference(value: object) -> bool:
    """判断文本是否包含已移除环境标记。"""
    text = str(value or "").strip().casefold()
    return any(environment in text for environment in REMOVED_ENVIRONMENTS)


def ensure_environment_allowed(environment: str) -> None:
    """拒绝任何已移除环境。"""
    if environment.strip().casefold() in REMOVED_ENVIRONMENTS:
        raise ValueError("prod 环境已永久移除，禁止操作")


def ensure_url_allowed(url: str) -> None:
    """拒绝指向已知生产服务的完整 URL。"""
    hostname = (urlparse(url.strip()).hostname or "").casefold()
    if hostname in FORBIDDEN_PRODUCTION_HOSTS or hostname.startswith("prod."):
        raise ValueError("prod 环境已永久移除，禁止访问生产地址")


def ensure_cache_value_allowed(value: object) -> None:
    """拒绝把带已移除环境标记的值写入本地缓存。"""
    if contains_removed_environment_reference(value):
        raise ValueError("prod 环境已永久移除，禁止缓存相关数据")
