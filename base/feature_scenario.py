"""SQL、API 与断言步骤组成的可复用功能测试场景。"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Union

try:
    from .api_request import ApiTemplate, execute_api_template, load_api_templates
    from .database_config import DatabaseConnectionConfig
    from .sql_data import SqlTemplate, execute_sql_template, load_sql_templates
except ImportError:  # Support direct execution imports.
    from api_request import ApiTemplate, execute_api_template, load_api_templates
    from database_config import DatabaseConnectionConfig
    from sql_data import SqlTemplate, execute_sql_template, load_sql_templates


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCENARIOS_FILE = PROJECT_ROOT / "cache" / "feature_scenarios.json"
STEP_TYPES = ("sql", "api", "extract", "assert")
ASSERT_OPERATORS = (
    "equals",
    "not_equals",
    "exists",
    "not_exists",
    "contains",
    "greater_than",
    "less_than",
)
VALUE_PATTERN = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


class ScenarioExecutionError(RuntimeError):
    """场景步骤执行或断言失败。"""


@dataclass(frozen=True)
class ScenarioStep:
    step_id: str
    step_type: str
    title: str
    config: Dict[str, object]
    cleanup: bool = False

    @classmethod
    def from_mapping(cls, value: object) -> "ScenarioStep | None":
        if not isinstance(value, dict):
            return None
        step_id = str(value.get("step_id", "")).strip()
        step_type = str(value.get("step_type", "")).strip()
        title = str(value.get("title", "")).strip()
        config = value.get("config")
        if (
            not step_id
            or step_type not in STEP_TYPES
            or not title
            or not isinstance(config, dict)
        ):
            return None
        return cls(step_id, step_type, title, dict(config), bool(value.get("cleanup")))


@dataclass(frozen=True)
class FeatureScenario:
    scenario_id: str
    title: str
    steps: tuple[ScenarioStep, ...]

    @classmethod
    def from_mapping(cls, value: object) -> "FeatureScenario | None":
        if not isinstance(value, dict):
            return None
        scenario_id = str(value.get("scenario_id", "")).strip()
        title = str(value.get("title", "")).strip()
        values = value.get("steps")
        if not scenario_id or not title or not isinstance(values, list):
            return None
        steps = tuple(
            step
            for item in values
            if (step := ScenarioStep.from_mapping(item)) is not None
        )
        if len(steps) != len(values):
            return None
        return cls(scenario_id, title, steps)


def load_feature_scenarios(
    path: Union[str, Path] = SCENARIOS_FILE,
) -> List[FeatureScenario]:
    scenario_path = Path(path)
    if not scenario_path.exists():
        return []
    try:
        data = json.loads(scenario_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    values = data.get("feature_scenarios") if isinstance(data, dict) else None
    if not isinstance(values, list):
        return []
    scenarios = [
        scenario
        for item in values
        if (scenario := FeatureScenario.from_mapping(item)) is not None
    ]
    return sorted(scenarios, key=lambda scenario: scenario.title.casefold())


def _write_feature_scenarios(
    scenarios: Sequence[FeatureScenario],
    path: Union[str, Path],
) -> None:
    scenario_path = Path(path)
    scenario_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = scenario_path.with_suffix(f"{scenario_path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(
            {"feature_scenarios": [asdict(scenario) for scenario in scenarios]},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(scenario_path)


def save_feature_scenario(
    title: str,
    steps: Sequence[ScenarioStep],
    *,
    scenario_id: Optional[str] = None,
    path: Union[str, Path] = SCENARIOS_FILE,
) -> FeatureScenario:
    normalized_title = title.strip()
    if not normalized_title:
        raise ValueError("场景标题不能为空")
    if not steps:
        raise ValueError("场景至少需要一个步骤")
    if any(step.step_type not in STEP_TYPES for step in steps):
        raise ValueError("场景包含不支持的步骤类型")

    scenarios = load_feature_scenarios(path)
    existing_id = (scenario_id or "").strip()
    if any(
        scenario.title.casefold() == normalized_title.casefold()
        and scenario.scenario_id != existing_id
        for scenario in scenarios
    ):
        raise ValueError("已存在同名功能场景")
    saved = FeatureScenario(
        existing_id or uuid.uuid4().hex,
        normalized_title,
        tuple(steps),
    )
    remaining = [
        scenario for scenario in scenarios if scenario.scenario_id != saved.scenario_id
    ]
    remaining.append(saved)
    remaining.sort(key=lambda scenario: scenario.title.casefold())
    _write_feature_scenarios(remaining, path)
    return saved


def delete_feature_scenario(
    scenario_id: str,
    path: Union[str, Path] = SCENARIOS_FILE,
) -> None:
    scenarios = load_feature_scenarios(path)
    remaining = [
        scenario for scenario in scenarios if scenario.scenario_id != scenario_id
    ]
    if len(remaining) == len(scenarios):
        raise ValueError("所选功能场景不存在")
    _write_feature_scenarios(remaining, path)


def new_step(
    step_type: str,
    title: str,
    config: Mapping[str, object],
    *,
    cleanup: bool = False,
) -> ScenarioStep:
    if step_type not in STEP_TYPES:
        raise ValueError("不支持的步骤类型")
    if not title.strip():
        raise ValueError("步骤标题不能为空")
    return ScenarioStep(uuid.uuid4().hex, step_type, title.strip(), dict(config), cleanup)


def scenario_needs_database(scenario: FeatureScenario) -> bool:
    return any(step.step_type == "sql" for step in scenario.steps)


def resolve_path(value: object, path: str) -> object:
    """按点分路径读取字典或列表值。"""
    current = value
    normalized = path.strip()
    if not normalized:
        return current
    for segment in normalized.split("."):
        if isinstance(current, Mapping):
            if segment not in current:
                raise ValueError(f"找不到字段：{path}")
            current = current[segment]
        elif isinstance(current, (list, tuple)):
            try:
                current = current[int(segment)]
            except (ValueError, IndexError) as error:
                raise ValueError(f"找不到列表项：{path}") from error
        else:
            raise ValueError(f"无法继续读取字段：{path}")
    return current


def _render_expected(value: object, context: Mapping[str, object]) -> object:
    if not isinstance(value, str):
        return value
    match = VALUE_PATTERN.fullmatch(value.strip())
    if match:
        name = match.group(1)
        if name not in context:
            raise ValueError(f"缺少场景变量：{name}")
        return context[name]

    def replace(parameter_match: re.Match[str]) -> str:
        name = parameter_match.group(1)
        if name not in context:
            raise ValueError(f"缺少场景变量：{name}")
        return str(context[name])

    rendered = VALUE_PATTERN.sub(replace, value)
    try:
        return json.loads(rendered)
    except json.JSONDecodeError:
        return rendered


def _assert_value(actual: object, operator: str, expected: object) -> None:
    if operator == "equals":
        passed = actual == expected
    elif operator == "not_equals":
        passed = actual != expected
    elif operator == "contains":
        try:
            passed = expected in actual  # type: ignore[operator]
        except TypeError:
            passed = False
    elif operator == "greater_than":
        passed = actual > expected  # type: ignore[operator]
    elif operator == "less_than":
        passed = actual < expected  # type: ignore[operator]
    else:
        raise ValueError(f"不支持的断言操作：{operator}")
    if not passed:
        raise AssertionError(f"expected {operator} {expected!r}, actual={actual!r}")


def _template_by_id(templates: Sequence[object], template_id: object) -> object:
    for template in templates:
        if getattr(template, "template_id", None) == template_id:
            return template
    raise ValueError(f"找不到模板：{template_id}")


def _execute_step(
    step: ScenarioStep,
    context: Dict[str, object],
    *,
    environment: str,
    sql_templates: Sequence[SqlTemplate],
    api_templates: Sequence[ApiTemplate],
    database_connection: Optional[DatabaseConnectionConfig],
) -> None:
    if step.step_type == "sql":
        template = _template_by_id(sql_templates, step.config.get("template_id"))
        if database_connection is None:
            raise ValueError("SQL 步骤需要配置当前环境数据库")
        if "userid" not in context:
            raise ValueError("SQL 步骤缺少 userid 变量")
        result = execute_sql_template(
            template,  # type: ignore[arg-type]
            int(context["userid"]),
            database_connection,
            context,
        )
        last_rows = list(result.result_sets[-1]) if result.result_sets else []
        context["sql_rows"] = last_rows
        context["sql"] = last_rows[0] if last_rows else {}
        context["sql_result"] = {
            "statements": result.statements,
            "affected_rows": result.affected_rows,
            "result_rows": result.result_rows,
        }
        print(
            f"  SQL · {result.statements} statements · "
            f"{result.affected_rows} affected · {result.result_rows} rows"
        )
        return

    if step.step_type == "api":
        template = _template_by_id(api_templates, step.config.get("template_id"))
        result = execute_api_template(
            template,  # type: ignore[arg-type]
            context,
            environment,
        )
        context["http_status"] = result.status_code
        context["elapsed_ms"] = result.elapsed_ms
        context["response"] = result.decoded_body
        context["raw_response"] = result.response_text
        context["response_headers"] = result.response_headers
        print(f"  HTTP {result.status_code} · {result.elapsed_ms} ms")
        return

    if step.step_type == "extract":
        source = str(step.config.get("path", "")).strip()
        variable = str(step.config.get("variable", "")).strip()
        if not source or not variable:
            raise ValueError("提取步骤必须配置字段路径和变量名")
        context[variable] = resolve_path(context, source)
        print(f"  {source} → {variable}")
        return

    if step.step_type == "assert":
        path = str(step.config.get("path", "")).strip()
        operator = str(step.config.get("operator", "equals")).strip()
        if operator not in ASSERT_OPERATORS:
            raise ValueError("断言操作无效")
        if operator in ("exists", "not_exists"):
            try:
                resolve_path(context, path)
                exists = True
            except ValueError:
                exists = False
            passed = exists if operator == "exists" else not exists
            if not passed:
                raise AssertionError(f"字段 {path} 的存在性断言失败")
            print(f"  {path} {operator}")
            return
        actual = resolve_path(context, path)
        expected = _render_expected(step.config.get("expected"), context)
        _assert_value(actual, operator, expected)
        print(f"  {path} {operator} {expected!r}")
        return

    raise ValueError(f"不支持的步骤类型：{step.step_type}")


def execute_feature_scenario(
    scenario: FeatureScenario,
    *,
    environment: str,
    runtime_parameters: Optional[Mapping[str, object]] = None,
    database_connection: Optional[DatabaseConnectionConfig] = None,
    stop_requested: Optional[Callable[[], bool]] = None,
    progress_callback: Optional[Callable[[int, int, int], None]] = None,
    sql_templates: Optional[Sequence[SqlTemplate]] = None,
    api_templates: Optional[Sequence[ApiTemplate]] = None,
) -> Dict[str, object]:
    """执行场景主步骤；失败后仍执行标记为清理的步骤。"""
    context: Dict[str, object] = dict(runtime_parameters or {})
    available_sql = list(sql_templates) if sql_templates is not None else load_sql_templates()
    available_api = list(api_templates) if api_templates is not None else load_api_templates()
    failure: Optional[Exception] = None
    completed = 0
    successful = 0
    total = len(scenario.steps)
    print(f"[scenario] START · {scenario.title}")

    for index, step in enumerate(scenario.steps, 1):
        if stop_requested and stop_requested() and not step.cleanup:
            failure = failure or ScenarioExecutionError("用户已停止任务")
        if failure is not None and not step.cleanup:
            print(f"[{index}/{total}] SKIP · {step.title}")
            completed += 1
            if progress_callback:
                progress_callback(completed, total, successful)
            continue
        try:
            print(
                f"[{index}/{total}] {'CLEANUP' if step.cleanup else step.step_type.upper()}"
                f" · {step.title}"
            )
            _execute_step(
                step,
                context,
                environment=environment,
                sql_templates=available_sql,
                api_templates=available_api,
                database_connection=database_connection,
            )
            successful += 1
            print(f"[{index}/{total}] OK · {step.title}")
        except Exception as error:
            print(f"[{index}/{total}] FAIL · {step.title} · {error}")
            failure = failure or error
        finally:
            completed += 1
            if progress_callback:
                progress_callback(completed, total, successful)

    if failure is not None:
        raise ScenarioExecutionError(str(failure)) from failure
    print(f"[scenario] PASS · {scenario.title}")
    return context


def run_feature_scenario(
    *,
    scenario: FeatureScenario,
    environment: str,
    runtime_parameters: Optional[Mapping[str, object]] = None,
    database_connection: Optional[DatabaseConnectionConfig] = None,
    stop_requested: Optional[Callable[[], bool]] = None,
    progress_callback: Optional[Callable[[int, int, int], None]] = None,
) -> int:
    """适配图形界面工作线程的场景入口。"""
    execute_feature_scenario(
        scenario,
        environment=environment,
        runtime_parameters=runtime_parameters,
        database_connection=database_connection,
        stop_requested=stop_requested,
        progress_callback=progress_callback,
    )
    return 1
