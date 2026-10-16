"""可复用 SSH 主机配置和远程操作。"""

from __future__ import annotations

import json
import shlex
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Union

from .database_config import load_ssh_private_keys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SSH_HOSTS_FILE = PROJECT_ROOT / "cache" / "ssh_hosts.json"
AUTH_KEY_PREFERRED = "key_preferred"
AUTH_KEY_ONLY = "key_only"
AUTH_PASSWORD_ONLY = "password_only"
AUTH_TYPES = {AUTH_KEY_PREFERRED, AUTH_KEY_ONLY, AUTH_PASSWORD_ONLY}


@dataclass
class SshHostConfig:
    """一个 SSH 登录目标。"""

    host_id: str = ""
    name: str = ""
    host: str = ""
    port: int = 22
    username: str = ""
    auth_type: str = AUTH_KEY_PREFERRED
    private_key_id: str = ""
    password: str = ""
    passphrase: str = ""
    remark: str = ""

    def __post_init__(self) -> None:
        if not self.host_id:
            self.host_id = uuid.uuid4().hex

    @classmethod
    def from_mapping(cls, value: object) -> "SshHostConfig | None":
        if not isinstance(value, dict):
            return None
        host_id = str(value.get("host_id", "")).strip()
        name = str(value.get("name", "")).strip()
        host = str(value.get("host", "")).strip()
        username = str(value.get("username", "")).strip()
        if not host_id or not name or not host or not username:
            return None
        try:
            port = int(value.get("port", 22))
        except (TypeError, ValueError):
            port = 22
        auth_type = str(value.get("auth_type", AUTH_KEY_PREFERRED))
        if auth_type not in AUTH_TYPES:
            auth_type = AUTH_KEY_PREFERRED
        return cls(
            host_id=host_id,
            name=name,
            host=host,
            port=port,
            username=username,
            auth_type=auth_type,
            private_key_id=str(value.get("private_key_id", "")).strip(),
            password=str(value.get("password", "")),
            passphrase=str(value.get("passphrase", "")),
            remark=str(value.get("remark", "")).strip(),
        )


@dataclass(frozen=True)
class SshCommandResult:
    stdout: str
    stderr: str
    exit_status: int


@dataclass(frozen=True)
class SshHostTime:
    date_text: str
    epoch_second: int
    epoch_millisecond: int


def load_ssh_hosts(
    path: Union[str, Path] = SSH_HOSTS_FILE,
) -> list[SshHostConfig]:
    config_path = Path(path)
    if not config_path.exists():
        return []
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    values = data.get("ssh_hosts", []) if isinstance(data, dict) else []
    hosts = []
    for value in values:
        parsed = SshHostConfig.from_mapping(value)
        if parsed is not None:
            hosts.append(parsed)
    return sorted(hosts, key=lambda item: item.name.casefold())


def save_ssh_hosts(
    hosts: list[SshHostConfig],
    path: Union[str, Path] = SSH_HOSTS_FILE,
) -> None:
    for host in hosts:
        validate_ssh_host(host)
    config_path = Path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = config_path.with_suffix(f"{config_path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(
            {"ssh_hosts": [asdict(host) for host in hosts]},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(config_path)


def validate_ssh_host(host: SshHostConfig) -> None:
    for value, message in (
        (host.name, "主机名称不能为空"),
        (host.host, "主机地址不能为空"),
        (host.username, "SSH 用户名不能为空"),
    ):
        if not str(value).strip():
            raise ValueError(message)
    if not 1 <= int(host.port) <= 65535:
        raise ValueError("SSH 端口必须在 1 到 65535 之间")
    if host.auth_type not in AUTH_TYPES:
        raise ValueError("SSH 认证方式无效")
    if host.auth_type == AUTH_KEY_ONLY and not host.private_key_id:
        raise ValueError("仅私钥认证必须选择私钥")
    if host.auth_type == AUTH_PASSWORD_ONLY and not host.password:
        raise ValueError("仅密码认证必须填写密码")
    if host.auth_type == AUTH_KEY_PREFERRED:
        if not host.private_key_id and not host.password:
            raise ValueError("请至少选择私钥或填写密码")


def _private_key_path(host: SshHostConfig) -> str:
    if not host.private_key_id:
        return ""
    key = load_ssh_private_keys().get(host.private_key_id)
    if key is None:
        raise ValueError("主机引用的 SSH 私钥已不存在，请重新选择")
    if not Path(key.path).is_file():
        raise ValueError("SSH 私钥文件不存在，请重新导入")
    return key.path


def connect_ssh_host(host: SshHostConfig):
    """按配置建立 Paramiko 连接；不会使用 Agent 或自动搜索密钥。"""
    validate_ssh_host(host)
    try:
        import paramiko
    except ImportError as error:  # pragma: no cover
        raise RuntimeError("缺少 Paramiko，请先安装项目依赖") from error

    key_path = ""
    if host.auth_type != AUTH_PASSWORD_ONLY:
        key_path = _private_key_path(host)
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=host.host,
            port=host.port,
            username=host.username,
            key_filename=key_path or None,
            password=host.password or None,
            passphrase=host.passphrase or None,
            allow_agent=False,
            look_for_keys=False,
            timeout=10,
            banner_timeout=10,
            auth_timeout=10,
        )
    except Exception:
        client.close()
        raise
    return client


def test_ssh_host(host: SshHostConfig) -> str:
    started = time.perf_counter()
    client = connect_ssh_host(host)
    try:
        transport = client.get_transport()
        if transport is None or not transport.is_active():
            raise ConnectionError("SSH 连接未建立")
    finally:
        client.close()
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    return f"连接成功 · {host.username}@{host.host}:{host.port} · {elapsed_ms} ms"


def execute_ssh_command(
    host: SshHostConfig,
    command: str,
    *,
    timeout: int = 30,
) -> SshCommandResult:
    if not command.strip():
        raise ValueError("远程命令不能为空")
    client = connect_ssh_host(host)
    try:
        _stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        # Paramiko 明确要求在 recv_exit_status 前消费输出；否则大输出可能填满
        # SSH channel window 并永久等待。
        stdout_text = stdout.read().decode("utf-8", errors="replace")
        stderr_text = stderr.read().decode("utf-8", errors="replace")
        exit_status = stdout.channel.recv_exit_status()
        return SshCommandResult(
            stdout=stdout_text,
            stderr=stderr_text,
            exit_status=int(exit_status),
        )
    finally:
        client.close()


def get_ssh_host_time(host: SshHostConfig) -> SshHostTime:
    command = "date '+%Y-%m-%d %H:%M:%S'; date +%s; date +%s%3N"
    result = execute_ssh_command(host, command)
    if result.exit_status != 0:
        raise RuntimeError(result.stderr.strip() or "读取远程主机时间失败")
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if len(lines) < 2:
        raise RuntimeError("远程主机返回了无法识别的时间信息")
    try:
        epoch_second = int(lines[1])
        epoch_millisecond = int(lines[2]) if len(lines) > 2 else epoch_second * 1000
    except ValueError as error:
        raise RuntimeError("远程主机返回了无效时间戳") from error
    return SshHostTime(lines[0], epoch_second, epoch_millisecond)


def set_ssh_host_time(host: SshHostConfig, timestamp: int) -> SshHostTime:
    epoch_second = int(timestamp)
    if abs(epoch_second) >= 1_000_000_000_000:
        epoch_second //= 1000
    result = execute_ssh_command(host, f"date -s @{epoch_second}")
    if result.exit_status != 0:
        date_text = datetime.fromtimestamp(epoch_second).strftime("%Y-%m-%d %H:%M:%S")
        result = execute_ssh_command(host, f"date -s {shlex.quote(date_text)}")
    if result.exit_status != 0:
        raise RuntimeError(result.stderr.strip() or "修改远程主机时间失败")
    try:
        execute_ssh_command(host, "hwclock -w")
    except Exception:
        pass
    return get_ssh_host_time(host)
