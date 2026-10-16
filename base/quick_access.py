"""本地快捷访问链接与登录字段管理。"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Union
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parent.parent
QUICK_ACCESS_FILE = PROJECT_ROOT / "cache" / "quick_access.json"


@dataclass
class QuickAccessField:
    """快捷链接附带的一个登录或配置字段。"""

    key: str
    value: str

    @classmethod
    def from_mapping(cls, value: object) -> "QuickAccessField | None":
        if not isinstance(value, dict):
            return None
        key = str(value.get("key", "")).strip()
        if not key:
            return None
        return cls(key=key, value=str(value.get("value", "")))


@dataclass
class QuickAccessLink:
    """一个可检索、可置顶的快捷链接。"""

    link_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    name: str = ""
    url: str = ""
    category: str = ""
    remark: str = ""
    is_top: bool = False
    fields: list[QuickAccessField] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, value: object) -> "QuickAccessLink | None":
        if not isinstance(value, dict):
            return None
        link_id = str(value.get("link_id", "")).strip()
        name = str(value.get("name", "")).strip()
        url = str(value.get("url", "")).strip()
        if not link_id or not name or not url:
            return None
        fields = []
        for item in value.get("fields", []):
            parsed = QuickAccessField.from_mapping(item)
            if parsed is not None:
                fields.append(parsed)
        return cls(
            link_id=link_id,
            name=name,
            url=url,
            category=str(value.get("category", "")).strip(),
            remark=str(value.get("remark", "")).strip(),
            is_top=bool(value.get("is_top", False)),
            fields=fields,
        )


def _read_payload(path: Union[str, Path]) -> dict:
    config_path = Path(path)
    if not config_path.exists():
        return {}
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def load_quick_access(
    path: Union[str, Path] = QUICK_ACCESS_FILE,
) -> tuple[list[QuickAccessLink], list[str]]:
    """加载快捷链接和独立分类，损坏记录会被跳过。"""
    data = _read_payload(path)
    links: list[QuickAccessLink] = []
    for item in data.get("links", []):
        parsed = QuickAccessLink.from_mapping(item)
        if parsed is not None:
            links.append(parsed)
    categories = {
        str(item).strip()
        for item in data.get("categories", [])
        if str(item).strip()
    }
    categories.update(link.category for link in links if link.category)
    links.sort(key=lambda item: (not item.is_top, item.name.casefold()))
    return links, sorted(categories, key=str.casefold)


def save_quick_access(
    links: Iterable[QuickAccessLink],
    categories: Iterable[str],
    path: Union[str, Path] = QUICK_ACCESS_FILE,
) -> None:
    """原子保存快捷访问数据。"""
    normalized_links = list(links)
    for link in normalized_links:
        validate_quick_access_link(link)
    normalized_categories = sorted(
        {str(category).strip() for category in categories if str(category).strip()},
        key=str.casefold,
    )
    normalized_categories = sorted(
        set(normalized_categories)
        | {link.category for link in normalized_links if link.category},
        key=str.casefold,
    )
    config_path = Path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = config_path.with_suffix(f"{config_path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(
            {
                "links": [asdict(link) for link in normalized_links],
                "categories": normalized_categories,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(config_path)


def validate_quick_access_link(link: QuickAccessLink) -> None:
    """校验链接和字段名。"""
    if not link.name.strip():
        raise ValueError("链接名称不能为空")
    url = link.url.strip()
    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError("地址必须是完整的 http:// 或 https:// 链接")
    keys: set[str] = set()
    for item in link.fields:
        key = item.key.strip()
        if not key:
            raise ValueError("登录字段名不能为空")
        folded = key.casefold()
        if folded in keys:
            raise ValueError(f"登录字段名不能重复：{key}")
        keys.add(folded)


def quick_access_share_text(link: QuickAccessLink) -> str:
    """生成适合复制到聊天窗口的链接摘要。"""
    lines = [link.name, link.url]
    if link.category:
        lines.append(f"分类：{link.category}")
    lines.extend(f"{item.key}：{item.value}" for item in link.fields)
    if link.remark:
        lines.append(f"备注：{link.remark}")
    return "\n".join(lines)
