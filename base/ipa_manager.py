"""下载和缓存 IPA，通过 tidevice 完成 iOS 归因和安装。"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import uuid
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable, Optional, Sequence, Union
from urllib.parse import unquote, urlparse

import requests
from cryptography import x509


PROJECT_ROOT = Path(__file__).resolve().parent.parent
IPA_CACHE_DIR = PROJECT_ROOT / "cache" / "ipas"
IPA_CONFIG_FILE = PROJECT_ROOT / "cache" / "ipa_packages.json"
MAX_IPA_BYTES = 4 * 1024 * 1024 * 1024
_BUNDLE_ID_PATTERN = re.compile(r"^[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$")


@dataclass(frozen=True)
class IosDevice:
    """一台由 tidevice 返回的 iOS 设备。"""

    udid: str
    name: str = ""
    product_version: str = ""
    connection_type: str = ""


@dataclass(frozen=True)
class IpaSignatureCheck:
    """IPA 静态签名与描述文件预检结果。"""

    valid: bool
    bundle_id: str = ""
    profile_name: str = ""
    team_id: str = ""
    expires_at: str = ""
    certificate_expires_at: str = ""
    provisions_all_devices: bool = False
    provisioned_devices: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    @property
    def summary(self) -> str:
        if not self.valid:
            return "；".join(self.errors)
        scope = (
            "全部设备"
            if self.provisions_all_devices
            else f"{len(self.provisioned_devices)} 台已登记设备"
        )
        return f"{self.bundle_id} · {self.profile_name} · {scope} · 到期 {self.expires_at}"


@dataclass(frozen=True)
class CachedIpa:
    """一个 IPA 缓存条目。"""

    package_id: str
    name: str
    path: str
    md5: str
    bundle_id: str
    profile_name: str
    expires_at: str
    attribution: str = ""
    note: str = ""
    added_at: str = ""


@dataclass(frozen=True)
class IpaMetadata:
    """仅用于展示的包信息，不表示签名校验结果。"""

    bundle_id: str
    profile_name: str = ""
    expires_at: str = ""


@dataclass(frozen=True)
class CacheIpaResult:
    package: CachedIpa
    duplicate: bool
    metadata: IpaMetadata


@dataclass(frozen=True)
class IpaInstallResult:
    status: str
    bundle_id: str


class TideviceCommandError(RuntimeError):
    """tidevice 命令执行失败。"""


def _iso_datetime(value: object) -> str:
    if not isinstance(value, datetime):
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _utc_datetime(value: object) -> Optional[datetime]:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _embedded_profile(data: bytes) -> dict:
    """从 CMS 包装的 embedded.mobileprovision 中提取 plist。"""
    starts = [index for token in (b"<?xml", b"<plist") if (index := data.find(token)) >= 0]
    start = min(starts) if starts else -1
    end = data.rfind(b"</plist>")
    if start < 0 or end < start:
        raise ValueError("无法解析 embedded.mobileprovision")
    value = plistlib.loads(data[start : end + len(b"</plist>")])
    if not isinstance(value, dict):
        raise ValueError("embedded.mobileprovision 内容无效")
    return value


def _bundle_matches(application_identifier: str, bundle_id: str) -> bool:
    """匹配 TeamID.bundle 或带通配符的 application-identifier。"""
    _, separator, pattern = application_identifier.partition(".")
    if not separator:
        return False
    if pattern.endswith("*"):
        return bundle_id.startswith(pattern[:-1])
    return pattern == bundle_id


def verify_ipa_signature(
    ipa_path: Union[str, Path],
    device_udid: str = "",
    *,
    now: Optional[datetime] = None,
) -> IpaSignatureCheck:
    """预检 IPA 结构、描述文件、证书期限、Bundle ID 和设备授权范围。"""
    path = Path(ipa_path)
    if not path.is_file():
        return IpaSignatureCheck(False, errors=("IPA 文件不存在",))
    current_time = _utc_datetime(now or datetime.now(timezone.utc))
    assert current_time is not None
    errors: list[str] = []
    bundle_id = ""
    profile_name = ""
    team_id = ""
    profile_expiration: Optional[datetime] = None
    certificate_expiration: Optional[datetime] = None
    provisions_all_devices = False
    provisioned_devices: tuple[str, ...] = ()

    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            info_files = [
                name
                for name in names
                if len(PurePosixPath(name).parts) == 3
                and PurePosixPath(name).parts[0] == "Payload"
                and PurePosixPath(name).parts[1].endswith(".app")
                and PurePosixPath(name).name == "Info.plist"
            ]
            if len(info_files) != 1:
                raise ValueError("IPA 必须且只能包含一个 Payload/*.app")
            app_root = str(PurePosixPath(info_files[0]).parent)
            info = plistlib.loads(archive.read(info_files[0]))
            if not isinstance(info, dict):
                raise ValueError("Info.plist 内容无效")
            bundle_id = str(info.get("CFBundleIdentifier") or "").strip()
            if not _BUNDLE_ID_PATTERN.fullmatch(bundle_id):
                errors.append("Bundle ID 缺失或格式无效")
            executable = str(info.get("CFBundleExecutable") or "").strip()
            if not executable or f"{app_root}/{executable}" not in names:
                errors.append("应用主程序缺失")
            if f"{app_root}/_CodeSignature/CodeResources" not in names:
                errors.append("应用未包含代码签名资源")

            profile_path = f"{app_root}/embedded.mobileprovision"
            if profile_path not in names:
                errors.append("未找到 embedded.mobileprovision，无法侧载此 IPA")
                profile = {}
            else:
                profile = _embedded_profile(archive.read(profile_path))
    except (OSError, zipfile.BadZipFile, KeyError, plistlib.InvalidFileException, ValueError) as error:
        return IpaSignatureCheck(False, errors=(f"IPA 结构无效：{error}",))

    if profile:
        profile_name = str(profile.get("Name") or "未命名描述文件").strip()
        identifiers = profile.get("TeamIdentifier") or []
        if isinstance(identifiers, list) and identifiers:
            team_id = str(identifiers[0]).strip()
        profile_expiration = _utc_datetime(profile.get("ExpirationDate"))
        if profile_expiration is None:
            errors.append("描述文件缺少有效期")
        elif profile_expiration <= current_time:
            errors.append("描述文件已过期")
        creation = _utc_datetime(profile.get("CreationDate"))
        if creation is not None and creation > current_time:
            errors.append("描述文件尚未生效")

        entitlements = profile.get("Entitlements") or {}
        application_identifier = ""
        if isinstance(entitlements, dict):
            application_identifier = str(
                entitlements.get("application-identifier")
                or entitlements.get("com.apple.application-identifier")
                or ""
            ).strip()
        if not application_identifier or not _bundle_matches(application_identifier, bundle_id):
            errors.append("描述文件的应用标识与 Bundle ID 不匹配")

        raw_devices = profile.get("ProvisionedDevices") or []
        if isinstance(raw_devices, list):
            provisioned_devices = tuple(str(value).strip() for value in raw_devices if str(value).strip())
        provisions_all_devices = bool(profile.get("ProvisionsAllDevices"))
        if not provisions_all_devices and not provisioned_devices:
            errors.append("描述文件既未授权全部设备，也没有设备白名单")
        if device_udid and not provisions_all_devices and device_udid not in provisioned_devices:
            errors.append(f"当前设备 {device_udid} 不在描述文件白名单中")

        certificate_windows: list[tuple[datetime, datetime]] = []
        for raw_certificate in profile.get("DeveloperCertificates") or []:
            try:
                certificate = x509.load_der_x509_certificate(bytes(raw_certificate))
                starts = getattr(certificate, "not_valid_before_utc", None)
                expires = getattr(certificate, "not_valid_after_utc", None)
                certificate_start = _utc_datetime(starts or certificate.not_valid_before)
                certificate_end = _utc_datetime(expires or certificate.not_valid_after)
                if certificate_start is not None and certificate_end is not None:
                    certificate_windows.append((certificate_start, certificate_end))
            except (TypeError, ValueError):
                continue
        active_certificates = [
            expires
            for starts, expires in certificate_windows
            if starts <= current_time < expires
        ]
        if not active_certificates:
            errors.append("描述文件中没有仍在有效期内的签名证书")
        else:
            certificate_expiration = max(active_certificates)

    return IpaSignatureCheck(
        valid=not errors,
        bundle_id=bundle_id,
        profile_name=profile_name,
        team_id=team_id,
        expires_at=_iso_datetime(profile_expiration),
        certificate_expires_at=_iso_datetime(certificate_expiration),
        provisions_all_devices=provisions_all_devices,
        provisioned_devices=provisioned_devices,
        errors=tuple(errors),
    )


def read_ipa_metadata(ipa_path: Union[str, Path]) -> IpaMetadata:
    """读取包标识和可选描述信息，不检查签名、证书或设备白名单。"""
    path = Path(ipa_path)
    if not path.is_file():
        raise ValueError("IPA 文件不存在")
    if path.suffix.lower() != ".ipa":
        raise ValueError("只支持 .ipa 安装包")
    try:
        with zipfile.ZipFile(path) as archive:
            info_files = [
                name for name in archive.namelist()
                if len(PurePosixPath(name).parts) == 3
                and PurePosixPath(name).parts[0] == "Payload"
                and PurePosixPath(name).parts[1].endswith(".app")
                and PurePosixPath(name).name == "Info.plist"
            ]
            if len(info_files) != 1:
                raise ValueError("IPA 必须且只能包含一个 Payload/*.app")
            info = plistlib.loads(archive.read(info_files[0]))
            if not isinstance(info, dict):
                raise ValueError("Info.plist 内容无效")
            bundle_id = str(info.get("CFBundleIdentifier") or "").strip()
            if not bundle_id:
                raise ValueError("Bundle ID 缺失")
            profile_path = f"{PurePosixPath(info_files[0]).parent}/embedded.mobileprovision"
            try:
                profile = _embedded_profile(archive.read(profile_path))
            except (KeyError, ValueError, plistlib.InvalidFileException):
                profile = {}
            return IpaMetadata(
                bundle_id,
                str(profile.get("Name") or "").strip(),
                _iso_datetime(profile.get("ExpirationDate")),
            )
    except (OSError, zipfile.BadZipFile, KeyError, plistlib.InvalidFileException, ValueError) as error:
        raise ValueError(f"无法读取 IPA 包信息：{error}") from error


def file_md5(path: Union[str, Path]) -> str:
    digest = hashlib.md5()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _normalize_package(value: object) -> Optional[CachedIpa]:
    if not isinstance(value, dict):
        return None
    required = ("package_id", "name", "path", "md5", "bundle_id")
    if any(not str(value.get(key) or "").strip() for key in required):
        return None
    return CachedIpa(
        package_id=str(value["package_id"]).strip(),
        name=str(value["name"]).strip(),
        path=str(value["path"]).strip(),
        md5=str(value["md5"]).strip().lower(),
        bundle_id=str(value["bundle_id"]).strip(),
        profile_name=str(value.get("profile_name") or "").strip(),
        expires_at=str(value.get("expires_at") or "").strip(),
        attribution=str(value.get("attribution") or "").strip(),
        note=str(value.get("note") or "").strip(),
        added_at=str(value.get("added_at") or "").strip(),
    )


def load_cached_ipas(path: Union[str, Path] = IPA_CONFIG_FILE) -> list[CachedIpa]:
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


def _write_cached_ipas(
    packages: Iterable[CachedIpa], path: Union[str, Path] = IPA_CONFIG_FILE
) -> None:
    config_path = Path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = config_path.with_suffix(f"{config_path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps({"packages": [asdict(item) for item in packages]}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(config_path)


def cache_ipa(
    source: Union[str, Path],
    attribution: Optional[str] = "",
    *,
    display_name: str = "",
    config_path: Union[str, Path] = IPA_CONFIG_FILE,
    cache_dir: Union[str, Path] = IPA_CACHE_DIR,
) -> CacheIpaResult:
    """读取包信息后按 MD5 缓存 IPA，不做签名预检。"""
    source_path = Path(source)
    if not source_path.is_file():
        raise ValueError("请选择存在的 IPA 文件")
    if source_path.suffix.lower() != ".ipa":
        raise ValueError("只支持缓存 .ipa 安装包")
    metadata = read_ipa_metadata(source_path)

    checksum = file_md5(source_path)
    packages = load_cached_ipas(config_path)
    existing = next((item for item in packages if item.md5 == checksum), None)
    if existing is not None:
        if attribution is not None:
            index = packages.index(existing)
            existing = CachedIpa(**{**asdict(existing), "attribution": attribution.strip()})
            packages[index] = existing
            _write_cached_ipas(packages, config_path)
        return CacheIpaResult(existing, True, metadata)

    target_dir = Path(cache_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{checksum}.ipa"
    if source_path.resolve() != target_path.resolve():
        shutil.copy2(source_path, target_path)
    package = CachedIpa(
        package_id=str(uuid.uuid4()),
        name=display_name.strip() or source_path.name,
        path=str(target_path.resolve()),
        md5=checksum,
        bundle_id=metadata.bundle_id,
        profile_name=metadata.profile_name,
        expires_at=metadata.expires_at,
        attribution=(attribution or "").strip(),
        added_at=datetime.now(timezone.utc).isoformat(),
    )
    packages.insert(0, package)
    _write_cached_ipas(packages, config_path)
    return CacheIpaResult(package, False, metadata)


def download_and_cache_ipa(
    url: str,
    attribution: Optional[str] = "",
    *,
    config_path: Union[str, Path] = IPA_CONFIG_FILE,
    cache_dir: Union[str, Path] = IPA_CACHE_DIR,
    timeout: tuple[int, int] = (10, 300),
) -> CacheIpaResult:
    """下载到临时文件，读取包信息后进入正式缓存。"""
    cleaned = url.strip()
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("下载地址必须是有效的 http:// 或 https:// URL")
    filename = Path(unquote(parsed.path)).name or "download.ipa"
    if not filename.lower().endswith(".ipa"):
        filename += ".ipa"
    target_dir = Path(cache_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    temporary_path = target_dir / f".{uuid.uuid4().hex}.download.ipa"
    try:
        with requests.get(cleaned, stream=True, timeout=timeout, allow_redirects=True) as response:
            response.raise_for_status()
            length = int(response.headers.get("Content-Length") or 0)
            if length > MAX_IPA_BYTES:
                raise ValueError("IPA 超过 4 GiB 下载限制")
            downloaded = 0
            with temporary_path.open("wb") as stream:
                for block in response.iter_content(chunk_size=1024 * 1024):
                    if not block:
                        continue
                    downloaded += len(block)
                    if downloaded > MAX_IPA_BYTES:
                        raise ValueError("IPA 超过 4 GiB 下载限制")
                    stream.write(block)
        return cache_ipa(
            temporary_path,
            attribution,
            display_name=filename,
            config_path=config_path,
            cache_dir=cache_dir,
        )
    finally:
        temporary_path.unlink(missing_ok=True)


def update_cached_ipa(
    package_id: str,
    *,
    name: str,
    attribution: str = "",
    note: str = "",
    path: Union[str, Path] = IPA_CONFIG_FILE,
) -> CachedIpa:
    packages = load_cached_ipas(path)
    index = next((i for i, item in enumerate(packages) if item.package_id == package_id), -1)
    if index < 0:
        raise ValueError("未找到缓存安装包")
    current = packages[index]
    updated = CachedIpa(
        **{
            **asdict(current),
            "name": name.strip() or current.name,
            "attribution": attribution.strip(),
            "note": note.strip(),
        }
    )
    packages[index] = updated
    _write_cached_ipas(packages, path)
    return updated


def remove_cached_ipa(package_id: str, path: Union[str, Path] = IPA_CONFIG_FILE) -> None:
    packages = load_cached_ipas(path)
    remaining = [item for item in packages if item.package_id != package_id]
    if len(remaining) == len(packages):
        raise ValueError("未找到缓存安装包")
    _write_cached_ipas(remaining, path)


def _run_tidevice(
    arguments: Sequence[str],
    *,
    udid: str = "",
    timeout: int = 180,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> str:
    command = [sys.executable, "-m", "tidevice"]
    if udid.strip():
        command.extend(["-u", udid.strip()])
    command.extend(arguments)
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = runner(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            creationflags=creation_flags,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
    except subprocess.TimeoutExpired as error:
        raise TideviceCommandError("iOS 设备操作超时") from error
    except OSError as error:
        raise TideviceCommandError(f"无法启动 tidevice：{error}") from error
    output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
    if result.returncode != 0:
        raise TideviceCommandError(output or f"tidevice 执行失败（{result.returncode}）")
    return result.stdout.strip()


def list_ios_devices() -> list[IosDevice]:
    output = _run_tidevice(["list", "--json"], timeout=30)
    try:
        values = json.loads(output or "[]")
    except json.JSONDecodeError as error:
        raise TideviceCommandError("tidevice 返回了无法识别的设备列表") from error
    if not isinstance(values, list):
        return []
    devices: list[IosDevice] = []
    for value in values:
        if not isinstance(value, dict) or not str(value.get("udid") or "").strip():
            continue
        devices.append(
            IosDevice(
                udid=str(value["udid"]).strip(),
                name=str(value.get("name") or value.get("serial") or "iPhone").strip(),
                product_version=str(value.get("product_version") or "").strip(),
                connection_type=str(value.get("conn_type") or "").strip(),
            )
        )
    return devices


def _validated_install(udid: str, ipa_path: Union[str, Path]) -> IpaInstallResult:
    cleaned_udid = udid.strip()
    if not cleaned_udid:
        raise ValueError("请先连接并选择 iOS 设备")
    metadata = read_ipa_metadata(ipa_path)
    _run_tidevice(["install", str(Path(ipa_path))], udid=cleaned_udid, timeout=600)
    return IpaInstallResult("installed", metadata.bundle_id)


def install_ipa(udid: str, ipa_path: Union[str, Path]) -> IpaInstallResult:
    """通过 tidevice 安装 IPA，由设备判断是否允许安装。"""
    return _validated_install(udid, ipa_path)


def open_ios_attribution_url(udid: str, url: str) -> None:
    """通过 Web Inspector 打开 Safari URL，兼容新版 iOS，不挂载开发者镜像。"""
    cleaned_udid = udid.strip()
    if not cleaned_udid:
        raise ValueError("请先连接并选择 iOS 设备")
    cleaned = url.strip()
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("归因链接必须是有效的 http:// 或 https:// 地址")
    _run_ios_safari(cleaned_udid, cleaned)


def _ios_python() -> str:
    runtime = PROJECT_ROOT / "cache" / "ios-runtime"
    executable = runtime / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if executable.is_file():
        return str(executable)
    if importlib.util.find_spec("pymobiledevice3") is not None:
        return sys.executable
    raise TideviceCommandError(
        "未安装 Safari 控制依赖，请按 README 的 iOS 运行环境步骤安装 requirements-ios.txt。"
    )


def _run_ios_safari(
    udid: str,
    url: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> None:
    command = [_ios_python(), str(PROJECT_ROOT / "tools" / "ios_safari.py")]
    try:
        result = runner(
            command,
            input=json.dumps({"udid": udid, "url": url}),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=90, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
    except subprocess.TimeoutExpired as error:
        raise TideviceCommandError("Safari 打开链接超时，请检查手机网络及 Web 检查器、远程自动化设置。") from error
    except OSError as error:
        raise TideviceCommandError(f"无法启动 Safari 控制工具：{error}") from error
    try:
        payload = json.loads(result.stdout.strip())
    except (json.JSONDecodeError, AttributeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    if result.returncode != 0 or payload.get("status") != "opened" or payload.get("udid") != udid:
        message = payload.get("message") or result.stderr.strip() or "Safari 控制工具未确认链接已打开"
        raise TideviceCommandError(f"Safari 归因链接打开失败：{message}")


def attribute_and_install_ipa(
    udid: str, url: str, ipa_path: Union[str, Path]
) -> IpaInstallResult:
    """读取包信息后打开归因链接并安装 IPA，不做签名预检。"""
    cleaned_udid = udid.strip()
    if not cleaned_udid:
        raise ValueError("请先连接并选择 iOS 设备")
    metadata = read_ipa_metadata(ipa_path)
    open_ios_attribution_url(cleaned_udid, url)
    _run_tidevice(["install", str(Path(ipa_path))], udid=cleaned_udid, timeout=600)
    return IpaInstallResult("installed", metadata.bundle_id)
