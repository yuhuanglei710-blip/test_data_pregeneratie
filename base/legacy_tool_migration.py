"""把旧 Java 测试平台的快捷访问与 SSH 数据迁移到桌面端。"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pymysql
from pymysql.cursors import DictCursor

from .database_config import import_ssh_private_key
from .local_tool_config import (
    QUICK_ACCESS_FILE,
    SSH_HOSTS_FILE,
    SSH_PRIVATE_KEY_DIR,
    SSH_PRIVATE_KEYS_FILE,
    env_value,
)
from .quick_access import (
    QuickAccessField,
    QuickAccessLink,
    load_quick_access,
    save_quick_access,
)
from .ssh_host import (
    AUTH_KEY_ONLY,
    AUTH_KEY_PREFERRED,
    AUTH_PASSWORD_ONLY,
    SshHostConfig,
    load_ssh_hosts,
    save_ssh_hosts,
)


AUTH_TYPE_MAP = {
    0: AUTH_KEY_PREFERRED,
    1: AUTH_KEY_ONLY,
    2: AUTH_PASSWORD_ONLY,
}


@dataclass(frozen=True)
class MigrationResult:
    links: int
    categories: int
    fields: int
    hosts: int
    private_keys: int
    backups: tuple[str, ...]


def _legacy_application_text() -> str:
    source_root = Path(env_value("LEGACY_TEST_TOOL_ROOT", "D:/test_tool/test_tool"))
    application_file = source_root / "server" / "src" / "main" / "resources" / "application.yml"
    try:
        return application_file.read_text(encoding="utf-8")
    except OSError:
        return ""


def _placeholder_default(text: str, name: str, default: str) -> str:
    match = re.search(r"\$\{" + re.escape(name) + r":([^}]+)\}", text)
    return match.group(1).strip() if match else default


def _connection_parameters() -> dict:
    application_text = _legacy_application_text()
    host = env_value(
        "LEGACY_TEST_TOOL_DB_HOST",
        _placeholder_default(application_text, "DB_HOST", "127.0.0.1"),
    )
    # Docker 内部默认主机名在桌面端不可用，迁移时走本机映射端口。
    if host in {"mysql", "localhost"}:
        host = "127.0.0.1"
    port_text = env_value(
        "LEGACY_TEST_TOOL_DB_PORT",
        _placeholder_default(application_text, "DB_PORT", "3306"),
    )
    try:
        port = int(port_text)
    except ValueError as error:
        raise ValueError("LEGACY_TEST_TOOL_DB_PORT 必须是数字") from error
    return {
        "host": host,
        "port": port,
        "user": env_value(
            "LEGACY_TEST_TOOL_DB_USER",
            _placeholder_default(application_text, "DB_USER", "root"),
        ),
        "password": env_value(
            "LEGACY_TEST_TOOL_DB_PASSWORD",
            _placeholder_default(application_text, "DB_PASSWORD", ""),
        ),
        "database": env_value(
            "LEGACY_TEST_TOOL_DB_NAME",
            _placeholder_default(application_text, "DB_NAME", "test_tool"),
        ),
        "charset": "utf8mb4",
        "connect_timeout": 5,
        "read_timeout": 10,
        "cursorclass": DictCursor,
    }


def _read_legacy_rows() -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    connection = pymysql.connect(**_connection_parameters())
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, name, url, category, remark, is_top "
                "FROM ql_link WHERE del_flag=0 ORDER BY is_top DESC, sort, id"
            )
            links = list(cursor.fetchall())
            cursor.execute(
                "SELECT link_id, field_key, field_value "
                "FROM ql_link_field WHERE del_flag=0 ORDER BY link_id, sort, id"
            )
            fields = list(cursor.fetchall())
            cursor.execute(
                "SELECT name FROM ql_link_category "
                "WHERE del_flag=0 ORDER BY sort, id"
            )
            categories = list(cursor.fetchall())
            cursor.execute(
                "SELECT id, name, host, port, username, password, private_key, "
                "passphrase, auth_type, remark "
                "FROM ssh_host WHERE del_flag=0 ORDER BY id"
            )
            hosts = list(cursor.fetchall())
        return links, fields, categories, hosts
    finally:
        connection.close()


def _backup_file(path: Path) -> str:
    if not path.is_file():
        return ""
    suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(f"{path.name}.{suffix}.bak")
    shutil.copy2(path, backup)
    return str(backup)


def _migrate_links(
    link_rows: list[dict],
    field_rows: list[dict],
    category_rows: list[dict],
) -> tuple[int, int, int]:
    fields_by_link: dict[int, dict[str, QuickAccessField]] = {}
    for row in field_rows:
        link_id = int(row["link_id"])
        key = str(row.get("field_key") or "").strip()
        if not key:
            continue
        # 桌面端按字段名（忽略大小写）保持唯一，后出现的值覆盖前值。
        fields_by_link.setdefault(link_id, {})[key.casefold()] = QuickAccessField(
            key=key,
            value=str(row.get("field_value") or ""),
        )

    migrated = []
    for row in link_rows:
        legacy_id = int(row["id"])
        migrated.append(
            QuickAccessLink(
                link_id=f"legacy-{legacy_id}",
                name=str(row.get("name") or "").strip(),
                url=str(row.get("url") or "").strip(),
                category=str(row.get("category") or "").strip(),
                remark=str(row.get("remark") or "").strip(),
                is_top=bool(row.get("is_top")),
                fields=list(fields_by_link.get(legacy_id, {}).values()),
            )
        )

    existing_links, existing_categories = load_quick_access()
    migrated_ids = {link.link_id for link in migrated}
    merged_links = [
        link for link in existing_links if link.link_id not in migrated_ids
    ] + migrated
    categories = set(existing_categories)
    categories.update(
        str(row.get("name") or "").strip()
        for row in category_rows
        if str(row.get("name") or "").strip()
    )
    save_quick_access(merged_links, categories)
    return len(migrated), len(categories), sum(len(link.fields) for link in migrated)


def _write_legacy_private_key(host_id: int, content: str) -> str:
    SSH_PRIVATE_KEY_DIR.mkdir(parents=True, exist_ok=True)
    key_path = SSH_PRIVATE_KEY_DIR / f"legacy_host_{host_id}.key"
    normalized = content.replace("\r\n", "\n").rstrip() + "\n"
    key_path.write_text(normalized, encoding="utf-8")
    return import_ssh_private_key(key_path).key_id


def _migrate_hosts(host_rows: list[dict]) -> tuple[int, int]:
    migrated = []
    private_key_count = 0
    for row in host_rows:
        legacy_id = int(row["id"])
        private_key = str(row.get("private_key") or "")
        private_key_id = ""
        if private_key.strip():
            private_key_id = _write_legacy_private_key(legacy_id, private_key)
            private_key_count += 1
        auth_type = AUTH_TYPE_MAP.get(
            int(row.get("auth_type") or 0),
            AUTH_KEY_PREFERRED,
        )
        migrated.append(
            SshHostConfig(
                host_id=f"legacy-{legacy_id}",
                name=str(row.get("name") or "").strip(),
                host=str(row.get("host") or "").strip(),
                port=int(row.get("port") or 22),
                username=str(row.get("username") or "").strip(),
                auth_type=auth_type,
                private_key_id=private_key_id,
                password=str(row.get("password") or ""),
                passphrase=str(row.get("passphrase") or ""),
                remark=str(row.get("remark") or "").strip(),
            )
        )
    existing_hosts = load_ssh_hosts()
    migrated_ids = {host.host_id for host in migrated}
    merged_hosts = [
        host for host in existing_hosts if host.host_id not in migrated_ids
    ] + migrated
    save_ssh_hosts(merged_hosts)
    return len(migrated), private_key_count


def migrate_legacy_tool_data() -> MigrationResult:
    """执行幂等迁移；重复执行会更新 legacy-* 记录并保留本地新增数据。"""
    link_rows, field_rows, category_rows, host_rows = _read_legacy_rows()
    backups = tuple(
        value
        for value in (
            _backup_file(QUICK_ACCESS_FILE),
            _backup_file(SSH_HOSTS_FILE),
            _backup_file(SSH_PRIVATE_KEYS_FILE),
        )
        if value
    )
    links, categories, fields = _migrate_links(
        link_rows,
        field_rows,
        category_rows,
    )
    hosts, private_keys = _migrate_hosts(host_rows)
    return MigrationResult(
        links=links,
        categories=categories,
        fields=fields,
        hosts=hosts,
        private_keys=private_keys,
        backups=backups,
    )


def main() -> None:
    result = migrate_legacy_tool_data()
    print(
        "迁移完成："
        f"快捷链接 {result.links}，分类 {result.categories}，字段 {result.fields}，"
        f"SSH 主机 {result.hosts}，私钥 {result.private_keys}"
    )
    if result.backups:
        print(f"已备份原文件 {len(result.backups)} 个")


if __name__ == "__main__":
    main()
