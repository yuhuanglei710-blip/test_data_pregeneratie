"""可复用 API 请求模板的保存、渲染与发送。"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Union

import requests


PROJECT_ROOT = Path(__file__).resolve().parent.parent
API_TEMPLATES_FILE = PROJECT_ROOT / "cache" / "api_templates.json"
SUPPORTED_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")
PARAMETER_PATTERN = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
MAX_RESPONSE_LOG_LENGTH = 20_000


@dataclass(frozen=True)
class ApiTemplate:
    """一条可复用的 HTTP API 请求模板。"""

    template_id: str
    title: str
    method: str
    url: str
    headers: str = "{}"
    body: str = ""
    timeout: int = 30

    @classmethod
    def from_mapping(cls, value: object) -> "ApiTemplate | None":
        if not isinstance(value, dict):
            return None
        template_id = str(value.get("template_id", "")).strip()
        title = str(value.get("title", "")).strip()
        method = str(value.get("method", "")).strip().upper()
        url = str(value.get("url", "")).strip()
        headers = str(value.get("headers", "{}"))
        body = str(value.get("body", ""))
        try:
            timeout = int(value.get("timeout", 30))
        except (TypeError, ValueError):
            return None
        if (
            not template_id
            or not title
            or method not in SUPPORTED_METHODS
            or not url
            or timeout <= 0
        ):
            return None
        return cls(template_id, title, method, url, headers, body, timeout)


@dataclass(frozen=True)
class ApiExecutionResult:
    """一次 API 请求的响应摘要。"""

    status_code: int
    elapsed_ms: int
    response_text: str
    response_headers: Dict[str, str]


def load_api_templates(
    path: Union[str, Path] = API_TEMPLATES_FILE,
) -> List[ApiTemplate]:
    template_path = Path(path)
    if not template_path.exists():
        return []
    try:
        data = json.loads(template_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    values = data.get("api_templates") if isinstance(data, dict) else None
    if not isinstance(values, list):
        return []
    templates = [
        template
        for value in values
        if (template := ApiTemplate.from_mapping(value)) is not None
    ]
    return sorted(templates, key=lambda template: template.title.casefold())


def _write_api_templates(
    templates: List[ApiTemplate],
    path: Union[str, Path],
) -> None:
    template_path = Path(path)
    template_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = template_path.with_suffix(f"{template_path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(
            {"api_templates": [asdict(template) for template in templates]},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(template_path)


def _parse_headers(headers: str) -> Dict[str, str]:
    try:
        parsed = json.loads(headers or "{}")
    except json.JSONDecodeError as error:
        raise ValueError(f"Headers 必须是合法 JSON：{error.msg}") from error
    if not isinstance(parsed, dict):
        raise ValueError("Headers 必须是 JSON 对象")
    return {str(key): str(value) for key, value in parsed.items()}


def save_api_template(
    title: str,
    method: str,
    url: str,
    headers: str = "{}",
    body: str = "",
    timeout: int = 30,
    *,
    template_id: Optional[str] = None,
    path: Union[str, Path] = API_TEMPLATES_FILE,
) -> ApiTemplate:
    """新增或更新一条 API 模板。"""
    normalized_title = title.strip()
    normalized_method = method.strip().upper()
    normalized_url = url.strip()
    if not normalized_title:
        raise ValueError("API 标题不能为空")
    if normalized_method not in SUPPORTED_METHODS:
        raise ValueError("不支持的请求方法")
    if not normalized_url.startswith(("http://", "https://")):
        raise ValueError("URL 必须以 http:// 或 https:// 开头")
    if int(timeout) <= 0:
        raise ValueError("超时时间必须大于 0 秒")
    _parse_headers(headers)

    templates = load_api_templates(path)
    existing_id = (template_id or "").strip()
    if any(
        template.title.casefold() == normalized_title.casefold()
        and template.template_id != existing_id
        for template in templates
    ):
        raise ValueError("已存在同名 API 模板")

    saved = ApiTemplate(
        template_id=existing_id or uuid.uuid4().hex,
        title=normalized_title,
        method=normalized_method,
        url=normalized_url,
        headers=headers.strip() or "{}",
        body=body,
        timeout=int(timeout),
    )
    remaining = [
        template for template in templates if template.template_id != saved.template_id
    ]
    remaining.append(saved)
    remaining.sort(key=lambda template: template.title.casefold())
    _write_api_templates(remaining, path)
    return saved


def delete_api_template(
    template_id: str,
    path: Union[str, Path] = API_TEMPLATES_FILE,
) -> None:
    templates = load_api_templates(path)
    remaining = [
        template for template in templates if template.template_id != template_id
    ]
    if len(remaining) == len(templates):
        raise ValueError("所选 API 模板不存在")
    _write_api_templates(remaining, path)


def template_parameter_names(template: ApiTemplate) -> List[str]:
    """按首次出现顺序返回模板中的占位参数名。"""
    names: List[str] = []
    for content in (template.url, template.headers, template.body):
        for name in PARAMETER_PATTERN.findall(content):
            if name not in names:
                names.append(name)
    return names


def parse_runtime_parameters(value: str) -> Dict[str, object]:
    """解析发送页填写的 JSON 参数对象。"""
    if not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError(f"运行参数必须是合法 JSON：{error.msg}") from error
    if not isinstance(parsed, dict):
        raise ValueError("运行参数必须是 JSON 对象")
    return parsed


def _render_value(value: str, parameters: Mapping[str, object]) -> str:
    missing: List[str] = []

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in parameters:
            missing.append(name)
            return match.group(0)
        parameter = parameters[name]
        if isinstance(parameter, (dict, list)):
            return json.dumps(parameter, ensure_ascii=False, separators=(",", ":"))
        if parameter is None:
            return "null"
        if isinstance(parameter, bool):
            return "true" if parameter else "false"
        return str(parameter)

    rendered = PARAMETER_PATTERN.sub(replace, value)
    if missing:
        raise ValueError(f"缺少 API 参数：{', '.join(dict.fromkeys(missing))}")
    return rendered


def execute_api_template(
    template: ApiTemplate,
    parameters: Mapping[str, object],
) -> ApiExecutionResult:
    """渲染并发送一次 HTTP 请求。"""
    url = _render_value(template.url, parameters)
    headers = _parse_headers(_render_value(template.headers, parameters))
    body = _render_value(template.body, parameters) if template.body else None
    started = time.perf_counter()
    response = requests.request(
        template.method,
        url,
        headers=headers,
        data=body,
        timeout=template.timeout,
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    response_text = response.text
    if len(response_text) > MAX_RESPONSE_LOG_LENGTH:
        response_text = (
            response_text[:MAX_RESPONSE_LOG_LENGTH]
            + f"\n… 响应已截断（原始 {len(response.text)} 字符）"
        )
    return ApiExecutionResult(
        response.status_code,
        elapsed_ms,
        response_text,
        dict(response.headers),
    )


def send_api_request(
    *,
    template: ApiTemplate,
    parameters: Mapping[str, object],
    stop_requested: Optional[Callable[[], bool]] = None,
    progress_callback: Optional[Callable[[int, int, int], None]] = None,
) -> int:
    """供界面工作线程调用的单次 API 请求任务。"""
    if stop_requested and stop_requested():
        print("用户已停止任务")
        return 0
    result = execute_api_template(template, parameters)
    print(
        f"[api] {template.method} · {result.status_code} · "
        f"{result.elapsed_ms} ms · {template.title}"
    )
    if result.response_text:
        print(result.response_text)
    successful = 1 if 200 <= result.status_code < 400 else 0
    if progress_callback:
        progress_callback(1, 1, successful)
    if not successful:
        raise RuntimeError(f"API 返回 HTTP {result.status_code}")
    return successful
