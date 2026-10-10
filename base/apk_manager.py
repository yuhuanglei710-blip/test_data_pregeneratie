"""缓存 Android 安装包，并通过 ADB 完成归因和安装。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Optional, Sequence, Union
from urllib.parse import urlparse

from .environment_policy import (
    contains_removed_environment_reference,
    ensure_cache_value_allowed,
    ensure_url_allowed,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
APK_CACHE_DIR = PROJECT_ROOT / "cache" / "apks"
APK_CONFIG_FILE = PROJECT_ROOT / "cache" / "apk_packages.json"
_PACKAGE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+$")
_SIGNATURE_PACKAGE_PATTERNS = (
    re.compile(r"Package\s+([A-Za-z0-9_.]+)\s+signatures", re.IGNORECASE),
    re.compile(
        r"Existing package\s+([A-Za-z0-9_.]+)\s+signatures",
        re.IGNORECASE,
    ),
)


@dataclass(frozen=True)
class AndroidDevice:
    """一台由 ``adb devices -l`` 返回的 Android 设备。"""

    serial: str
    status: str
    detail: str = ""


@dataclass(frozen=True)
class CachedApk:
    """一个持久化的 APK 缓存条目。"""

    package_id: str
    name: str
    path: str
    md5: str
    attribution: str = ""
    note: str = ""
    added_at: str = ""


@dataclass(frozen=True)
class CacheApkResult:
    """缓存操作结果；``duplicate`` 表示复用了相同 MD5 的条目。"""

    package: CachedApk
    duplicate: bool


@dataclass(frozen=True)
class ApkInstallResult:
    """APK 安装结果。"""

    status: str
    package_name: str = ""


class AdbCommandError(RuntimeError):
    """ADB 命令执行失败，并保留设备返回的可读信息。"""

    def __init__(self, message: str, output: str = "") -> None:
        super().__init__(message)
        self.output = output


def _normalize_package(value: object) -> Optional[CachedApk]:
    if not isinstance(value, dict):
        return None
    package_id = str(value.get("package_id") or value.get("id") or "").strip()
    name = str(value.get("name") or "").strip()
    path = str(value.get("path") or "").strip()
    checksum = str(value.get("md5") or "").strip().lower()
    if not package_id or not name or not path or not checksum:
        return None
    package = CachedApk(
        package_id=package_id,
        name=name,
        path=path,
        md5=checksum,
        attribution=str(value.get("attribution") or "").strip(),
        note=str(value.get("note") or "").strip(),
        added_at=str(value.get("added_at") or value.get("addedAt") or "").strip(),
    )
    if any(
        contains_removed_environment_reference(field)
        for field in asdict(package).values()
    ):
        return None
    return package


def load_cached_apks(
    path: Union[str, Path] = APK_CONFIG_FILE,
) -> list[CachedApk]:
    """加载缓存列表；损坏或不存在的配置会安全地返回空列表。"""
    config_path = Path(path)
    if not config_path.exists():
        return []
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    values = data.get("packages", []) if isinstance(data, dict) else []
    if not isinstance(values, list):
        return []
    return [package for value in values if (package := _normalize_package(value))]


def _write_cached_apks(
    packages: Iterable[CachedApk],
    path: Union[str, Path] = APK_CONFIG_FILE,
) -> None:
    packages = list(packages)
    for package in packages:
        for value in asdict(package).values():
            ensure_cache_value_allowed(value)
    config_path = Path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = config_path.with_suffix(f"{config_path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(
            {"packages": [asdict(package) for package in packages]},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(config_path)


def file_md5(path: Union[str, Path]) -> str:
    """流式计算文件 MD5，避免把大型 APK 一次性读入内存。"""
    digest = hashlib.md5()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def cache_apk(
    source: Union[str, Path],
    attribution: Optional[str] = "",
    *,
    config_path: Union[str, Path] = APK_CONFIG_FILE,
    cache_dir: Union[str, Path] = APK_CACHE_DIR,
) -> CacheApkResult:
    """按 MD5 缓存 APK；相同文件只保留一个条目。"""
    source_path = Path(source)
    ensure_cache_value_allowed(source_path.name)
    ensure_cache_value_allowed(attribution or "")
    if not source_path.is_file():
        raise ValueError("请选择存在的 APK 文件")
    if source_path.suffix.lower() != ".apk":
        raise ValueError("只支持缓存 .apk 安装包")

    checksum = file_md5(source_path)
    packages = load_cached_apks(config_path)
    existing = next((item for item in packages if item.md5 == checksum), None)
    if existing is not None:
        if attribution is not None:
            updated = CachedApk(
                **{
                    **asdict(existing),
                    "attribution": attribution.strip(),
                }
            )
            packages[packages.index(existing)] = updated
            _write_cached_apks(packages, config_path)
            existing = updated
        return CacheApkResult(existing, True)

    target_dir = Path(cache_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{checksum}.apk"
    if source_path.resolve() != target_path.resolve():
        shutil.copy2(source_path, target_path)
    package = CachedApk(
        package_id=str(uuid.uuid4()),
        name=source_path.name,
        path=str(target_path.resolve()),
        md5=checksum,
        attribution=(attribution or "").strip(),
        added_at=datetime.now(timezone.utc).isoformat(),
    )
    packages.insert(0, package)
    _write_cached_apks(packages, config_path)
    return CacheApkResult(package, False)


def update_cached_apk(
    package_id: str,
    *,
    name: str,
    attribution: str = "",
    note: str = "",
    path: Union[str, Path] = APK_CONFIG_FILE,
) -> CachedApk:
    """更新缓存条目的显示名称、归因链接和备注。"""
    for value in (name, attribution, note):
        ensure_cache_value_allowed(value)
    packages = load_cached_apks(path)
    index = next(
        (position for position, item in enumerate(packages) if item.package_id == package_id),
        -1,
    )
    if index < 0:
        raise ValueError("未找到缓存安装包")
    current = packages[index]
    updated = CachedApk(
        **{
            **asdict(current),
            "name": name.strip() or current.name,
            "attribution": attribution.strip(),
            "note": note.strip(),
        }
    )
    packages[index] = updated
    _write_cached_apks(packages, path)
    return updated


def remove_cached_apk(
    package_id: str,
    path: Union[str, Path] = APK_CONFIG_FILE,
) -> None:
    """移除缓存记录；实际 APK 文件保留，避免不可恢复地删除文件。"""
    packages = load_cached_apks(path)
    remaining = [item for item in packages if item.package_id != package_id]
    if len(remaining) == len(packages):
        raise ValueError("未找到缓存安装包")
    _write_cached_apks(remaining, path)


def adb_executable() -> str:
    """解析 ADB 路径，优先使用 ``ADB_PATH`` 环境变量。"""
    configured = os.environ.get("ADB_PATH", "").strip()
    executable = configured or shutil.which("adb")
    if not executable:
        raise RuntimeError("未找到 ADB，请配置 ADB_PATH 或把 adb 加入系统 PATH")
    return executable


def _run_adb(
    arguments: Sequence[str],
    *,
    timeout: int = 120,
    input_text: Optional[str] = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> str:
    command = [adb_executable(), *arguments]
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = runner(
            command,
            input=input_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            creationflags=creation_flags,
        )
    except subprocess.TimeoutExpired as error:
        raise AdbCommandError("ADB 操作超时") from error
    except OSError as error:
        raise AdbCommandError(f"无法启动 ADB：{error}") from error
    output = "\n".join(
        part.strip() for part in (result.stdout, result.stderr) if part.strip()
    )
    if result.returncode != 0:
        raise AdbCommandError(output or f"ADB 执行失败（{result.returncode}）", output)
    return output


def list_android_devices() -> list[AndroidDevice]:
    """列出 ADB 可见设备，包括未授权或离线设备。"""
    output = _run_adb(["devices", "-l"], timeout=15)
    devices: list[AndroidDevice] = []
    for raw_line in output.splitlines()[1:]:
        line = raw_line.strip()
        if not line or line.startswith("*"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        devices.append(AndroidDevice(parts[0], parts[1], " ".join(parts[2:])))
    return devices


def _device_arguments(serial: str, arguments: Sequence[str]) -> list[str]:
    cleaned = serial.strip()
    if not cleaned:
        raise ValueError("请先连接并选择 Android 设备")
    return ["-s", cleaned, *arguments]


def _signature_conflict_package(message: str) -> str:
    if "INSTALL_FAILED_UPDATE_INCOMPATIBLE" not in message.upper():
        return ""
    for pattern in _SIGNATURE_PACKAGE_PATTERNS:
        match = pattern.search(message)
        if match:
            return match.group(1)
    return ""


def install_apk(serial: str, apk_path: Union[str, Path]) -> ApkInstallResult:
    """允许覆盖及降级安装；签名冲突时返回旧包包名供界面确认。"""
    package_path = Path(apk_path)
    if not package_path.is_file():
        raise ValueError("缓存的 APK 文件不存在，请重新选择并缓存")
    try:
        _run_adb(
            _device_arguments(
                serial,
                ["install", "-r", "-d", str(package_path)],
            )
        )
    except AdbCommandError as error:
        package_name = _signature_conflict_package(error.output or str(error))
        if package_name:
            return ApkInstallResult("signature-conflict", package_name)
        raise
    return ApkInstallResult("installed")


def reinstall_apk(
    serial: str,
    apk_path: Union[str, Path],
    package_name: str,
) -> ApkInstallResult:
    """卸载同包名旧应用后重新安装 APK。"""
    if not _PACKAGE_NAME_PATTERN.fullmatch(package_name):
        raise ValueError("设备返回的包名无效，已拒绝卸载")
    package_path = Path(apk_path)
    if not package_path.is_file():
        raise ValueError("缓存的 APK 文件不存在，请重新选择并缓存")
    _run_adb(_device_arguments(serial, ["uninstall", package_name]), timeout=60)
    _run_adb(
        _device_arguments(serial, ["install", "-r", "-d", str(package_path)])
    )
    return ApkInstallResult("reinstalled", package_name)


def open_attribution_url(serial: str, url: str) -> None:
    """在所选 Android 设备上打开归因链接。"""
    cleaned = url.strip()
    ensure_cache_value_allowed(cleaned)
    ensure_url_allowed(cleaned)
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("归因链接必须是有效的 http:// 或 https:// 地址")
    # 通过 adb shell 的标准输入发送命令，避免超长链接受 Windows
    # CreateProcess 命令行长度限制影响。
    shell_command = (
        "am start -a android.intent.action.VIEW -d "
        f"{shlex.quote(cleaned)}\n"
    )
    _run_adb(
        _device_arguments(serial, ["shell"]),
        timeout=30,
        input_text=shell_command,
    )


def attribute_and_install(
    serial: str,
    url: str,
    apk_path: Union[str, Path],
) -> ApkInstallResult:
    """先打开归因链接，再安装对应 APK。"""
    open_attribution_url(serial, url)
    return install_apk(serial, apk_path)
