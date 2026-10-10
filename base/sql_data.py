"""命名 SQL 模板的保存、参数化与执行。"""

from __future__ import annotations

import json
import math
import re
import uuid
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Tuple, Union

try:
    from .database_config import DatabaseConnectionConfig, open_database_connection
except ImportError:  # Support ``python base/sql_data.py`` imports.
    from database_config import DatabaseConnectionConfig, open_database_connection


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SQL_TEMPLATES_FILE = PROJECT_ROOT / "cache" / "sql_templates.json"
PARAMETER_DECLARATION = re.compile(
    r"(?im)(^|;)(\s*)(?:(SET)(\s+))?"
    r"@([A-Za-z_][A-Za-z0-9_]*)(\s*=\s*)xxx\b",
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
    if not PARAMETER_DECLARATION.search(normalized_sql):
        raise ValueError("SQL 中必须至少包含一个 @参数名=xxx 声明")

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


def template_parameter_names(template: SqlTemplate) -> List[str]:
    """按声明首次出现的顺序返回 SQL 模板参数名。"""
    names: List[str] = []
    known_names: set[str] = set()
    for match in PARAMETER_DECLARATION.finditer(template.sql):
        name = match.group(5)
        normalized = name.casefold()
        if normalized not in known_names:
            known_names.add(normalized)
            names.append(name)
    return names


def parse_runtime_parameter(value: str) -> object:
    """把界面文本解析为常用 SQL 参数类型，普通文本保持为字符串。"""
    normalized = value.strip()
    if not normalized:
        raise ValueError("参数值不能为空")
    if normalized.casefold() == "null":
        return None
    if normalized.casefold() == "true":
        return True
    if normalized.casefold() == "false":
        return False
    try:
        parsed = json.loads(normalized)
    except json.JSONDecodeError:
        return normalized
    if isinstance(parsed, (dict, list)):
        return normalized
    return parsed


def _sql_literal(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (float, Decimal)):
        if not math.isfinite(float(value)):
            raise ValueError("SQL 参数不能是无穷大或 NaN")
        return str(value)
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    text = str(value)
    escaped = (
        text.replace("\\", "\\\\")
        .replace("'", "''")
        .replace("\0", "\\0")
        .replace("\r", "\\r")
        .replace("\n", "\\n")
    )
    return f"'{escaped}'"


def render_sql_template(
    template: SqlTemplate,
    user_id: Optional[int] = None,
    parameters: Optional[Mapping[str, object]] = None,
) -> str:
    """把 @参数名=xxx 声明替换为安全的 MySQL SET 语句。"""
    values = {
        str(name).casefold(): value
        for name, value in (parameters or {}).items()
    }
    if user_id is not None:
        values["userid"] = user_id

    missing: List[str] = []

    def replace_declaration(match: re.Match[str]) -> str:
        name = match.group(5)
        normalized_name = name.casefold()
        if normalized_name not in values:
            missing.append(name)
            return match.group(0)
        value = values[normalized_name]
        if normalized_name == "userid":
            if isinstance(value, bool):
                raise ValueError("User ID 必须是大于 0 的整数")
            try:
                value = int(str(value).replace(",", "").strip())
            except (TypeError, ValueError) as error:
                raise ValueError("User ID 必须是大于 0 的整数") from error
            if value <= 0:
                raise ValueError("User ID 必须是大于 0 的整数")
        set_keyword = (
            f"{match.group(3)}{match.group(4)}"
            if match.group(3)
            else "SET "
        )
        return (
            f"{match.group(1)}{match.group(2)}{set_keyword}"
            f"@{name}{match.group(6)}{_sql_literal(value)}"
        )

    rendered = PARAMETER_DECLARATION.sub(replace_declaration, template.sql)
    if missing:
        raise ValueError(f"缺少 SQL 参数：{', '.join(dict.fromkeys(missing))}")
    if not template_parameter_names(template):
        raise ValueError("SQL 中未找到 @参数名=xxx 声明")
    return rendered


def execute_sql_template(
    template: SqlTemplate,
    user_id: Optional[int],
    connection: DatabaseConnectionConfig,
    parameters: Optional[Mapping[str, object]] = None,
) -> SqlExecutionResult:
    """在当前环境业务库中以事务执行渲染后的 SQL。"""
    rendered_sql = render_sql_template(template, user_id, parameters)
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
    user_id: Optional[int] = None,
    parameters: Optional[Mapping[str, object]] = None,
    connection: DatabaseConnectionConfig,
    stop_requested: Optional[Callable[[], bool]] = None,
    progress_callback: Optional[Callable[[int, int, int], None]] = None,
) -> int:
    """供界面工作线程调用的单次功能数据生成任务。"""
    if stop_requested and stop_requested():
        print("用户已停止任务")
        return 0
    execute_sql_template(template, user_id, connection, parameters)
    user_label = f" · uid={user_id}" if user_id is not None else ""
    print(f"[sql] OK · {template.title}{user_label}")
    if progress_callback:
        progress_callback(1, 1, 1)
    return 1
