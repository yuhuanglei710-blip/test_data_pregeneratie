"""命名 SQL 模板的保存、参数化与执行。"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Union

try:
    from .database_config import DatabaseConnectionConfig, open_database_connection
except ImportError:  # Support ``python base/sql_data.py`` imports.
    from database_config import DatabaseConnectionConfig, open_database_connection


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SQL_TEMPLATES_FILE = PROJECT_ROOT / "cache" / "sql_templates.json"
USER_ID_PLACEHOLDER = re.compile(
    r"(@userid\s*=\s*)xxx\b",
    flags=re.IGNORECASE,
)
BARE_USER_ID_DECLARATION = re.compile(
    r"(?im)(^|;)(\s*)@userid\s*=\s*xxx\b",
)


@dataclass(frozen=True)
class SqlTemplate:
    """一条可复用的功能数据 SQL 模板。"""

    template_id: str
    title: str
    sql: str

    @classmethod
    def from_mapping(cls, value: object) -> "SqlTemplate | None":
        if not isinstance(value, dict):
            return None
        template_id = str(value.get("template_id", "")).strip()
        title = str(value.get("title", "")).strip()
        sql = str(value.get("sql", "")).strip()
        if not template_id or not title or not sql:
            return None
        return cls(template_id, title, sql)


@dataclass(frozen=True)
class SqlExecutionResult:
    """SQL 模板的执行摘要。"""

    statements: int
    affected_rows: int
    result_rows: int
    result_sets: Tuple[Tuple[Dict[str, object], ...], ...] = ()


def load_sql_templates(
    path: Union[str, Path] = SQL_TEMPLATES_FILE,
) -> List[SqlTemplate]:
    """读取按标题排序的 SQL 模板。"""
    template_path = Path(path)
    if not template_path.exists():
        return []
    try:
        data = json.loads(template_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    values = data.get("sql_templates") if isinstance(data, dict) else None
    if not isinstance(values, list):
        return []
    templates = [
        template
        for value in values
        if (template := SqlTemplate.from_mapping(value)) is not None
    ]
    return sorted(templates, key=lambda template: template.title.casefold())


def _write_sql_templates(
    templates: List[SqlTemplate],
    path: Union[str, Path],
) -> None:
    template_path = Path(path)
    template_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = template_path.with_suffix(f"{template_path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(
            {"sql_templates": [asdict(template) for template in templates]},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(template_path)


def save_sql_template(
    title: str,
    sql: str,
    *,
    template_id: Optional[str] = None,
    path: Union[str, Path] = SQL_TEMPLATES_FILE,
) -> SqlTemplate:
    """新增或更新一条 SQL 模板。"""
    normalized_title = title.strip()
    normalized_sql = sql.strip()
    if not normalized_title:
        raise ValueError("SQL 标题不能为空")
    if not normalized_sql:
        raise ValueError("SQL 内容不能为空")
    if not USER_ID_PLACEHOLDER.search(normalized_sql):
        raise ValueError("SQL 中必须包含 @userid=xxx 参数")

    templates = load_sql_templates(path)
    existing_id = (template_id or "").strip()
    if any(
        template.title.casefold() == normalized_title.casefold()
        and template.template_id != existing_id
        for template in templates
    ):
        raise ValueError("已存在同名 SQL 模板")

    saved = SqlTemplate(
        template_id=existing_id or uuid.uuid4().hex,
        title=normalized_title,
        sql=normalized_sql,
    )
    remaining = [
        template for template in templates if template.template_id != saved.template_id
    ]
    remaining.append(saved)
    remaining.sort(key=lambda template: template.title.casefold())
    _write_sql_templates(remaining, path)
    return saved


def delete_sql_template(
    template_id: str,
    path: Union[str, Path] = SQL_TEMPLATES_FILE,
) -> None:
    """删除指定 SQL 模板。"""
    templates = load_sql_templates(path)
    remaining = [
        template for template in templates if template.template_id != template_id
    ]
    if len(remaining) == len(templates):
        raise ValueError("所选 SQL 模板不存在")
    _write_sql_templates(remaining, path)


def render_sql_template(template: SqlTemplate, user_id: int) -> str:
    """把 @userid=xxx 中的 xxx 替换为经校验的整数 UID。"""
    if isinstance(user_id, bool) or int(user_id) <= 0:
        raise ValueError("User ID 必须是大于 0 的整数")
    rendered, bare_replacements = BARE_USER_ID_DECLARATION.subn(
        rf"\g<1>\g<2>SET @userid={int(user_id)}",
        template.sql,
    )
    rendered, replacements = USER_ID_PLACEHOLDER.subn(
        rf"\g<1>{int(user_id)}",
        rendered,
    )
    if bare_replacements + replacements == 0:
        raise ValueError("SQL 中未找到 @userid=xxx 参数")
    return rendered


def execute_sql_template(
    template: SqlTemplate,
    user_id: int,
    connection: DatabaseConnectionConfig,
) -> SqlExecutionResult:
    """在当前环境业务库中以事务执行渲染后的 SQL。"""
    rendered_sql = render_sql_template(template, user_id)
    statements = 0
    affected_rows = 0
    result_rows = 0
    result_sets: List[Tuple[Dict[str, object], ...]] = []
    with open_database_connection(connection, multi_statements=True) as database:
        try:
            with database.cursor() as cursor:
                cursor.execute(rendered_sql)
                while True:
                    statements += 1
                    if cursor.description is None:
                        affected_rows += max(0, int(cursor.rowcount))
                    else:
                        rows = cursor.fetchall()
                        columns = [str(column[0]) for column in cursor.description]
                        normalized_rows = tuple(
                            dict(row)
                            if isinstance(row, dict)
                            else dict(zip(columns, row))
                            for row in rows
                        )
                        result_rows += len(normalized_rows)
                        result_sets.append(normalized_rows)
                    if not cursor.nextset():
                        break
            database.commit()
        except Exception:
            database.rollback()
            raise
    return SqlExecutionResult(
        statements,
        affected_rows,
        result_rows,
        tuple(result_sets),
    )


def generate_feature_data(
    *,
    template: SqlTemplate,
    user_id: int,
    connection: DatabaseConnectionConfig,
    stop_requested: Optional[Callable[[], bool]] = None,
    progress_callback: Optional[Callable[[int, int, int], None]] = None,
) -> int:
    """供界面工作线程调用的单次功能数据生成任务。"""
    if stop_requested and stop_requested():
        print("用户已停止任务")
        return 0
    execute_sql_template(template, user_id, connection)
    print(f"[sql] OK · {template.title} · uid={user_id}")
    if progress_callback:
        progress_callback(1, 1, 1)
    return 1
