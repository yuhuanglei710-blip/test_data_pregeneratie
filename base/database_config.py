"""按环境隔离的 SSH 和 MySQL 连接配置。"""

from __future__ import annotations

import json
import select
import socketserver
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterator, Union

from .user import SUPPORTED_ENVIRONMENTS


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_CONNECTIONS_FILE = PROJECT_ROOT / "cache" / "database_connections.json"
SSH_PRIVATE_KEYS_FILE = PROJECT_ROOT / "cache" / "ssh_private_keys.json"


@dataclass(frozen=True)
class SshPrivateKey:
    """可被多个环境复用的 SSH 私钥记录。"""

    key_id: str
    name: str
    path: str


@dataclass
class DatabaseConnectionConfig:
    """单个环境的 SSH 隧道和 MySQL 参数。"""

    ssh_host: str = ""
    ssh_port: int = 22
    ssh_username: str = ""
    ssh_private_key_id: str = ""
    database_host: str = "127.0.0.1"
    database_port: int = 3306
    database_name: str = ""
    database_username: str = ""
    database_password: str = ""
    database_charset: str = "utf8mb4"

    @classmethod
    def from_mapping(cls, values: object) -> "DatabaseConnectionConfig":
        """从 JSON 数据创建配置，并补齐安全默认值。"""
        if not isinstance(values, dict):
            return cls()
        text_fields = {
            field: str(values.get(field, default)).strip()
            for field, default in (
                ("ssh_host", ""),
                ("ssh_username", ""),
                ("ssh_private_key_id", ""),
                ("database_host", "127.0.0.1"),
                ("database_name", ""),
                ("database_username", ""),
                ("database_charset", "utf8mb4"),
            )
        }
        text_fields["database_password"] = str(
            values.get("database_password", "")
        )
        return cls(
            **text_fields,
            ssh_port=_safe_port(values.get("ssh_port"), 22),
            database_port=_safe_port(values.get("database_port"), 3306),
        )


def _safe_port(value: object, default: int) -> int:
    """返回合法 TCP 端口，否则使用默认值。"""
    try:
        port = int(value)
    except (TypeError, ValueError):
        return default
    return port if 1 <= port <= 65535 else default


def _default_connections() -> Dict[str, DatabaseConnectionConfig]:
    """为每个环境创建空数据库配置。"""
    return {
        environment: DatabaseConnectionConfig()
        for environment in SUPPORTED_ENVIRONMENTS
    }


def load_ssh_private_keys(
    path: Union[str, Path] = SSH_PRIVATE_KEYS_FILE,
) -> Dict[str, SshPrivateKey]:
    """加载可复用的 SSH 私钥库。"""
    key_file = Path(path)
    if not key_file.exists():
        return {}
    try:
        data = json.loads(key_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    values = data.get("ssh_private_keys") if isinstance(data, dict) else None
    if not isinstance(values, list):
        return {}
    keys: Dict[str, SshPrivateKey] = {}
    for value in values:
        if not isinstance(value, dict):
            continue
        key_id = str(value.get("key_id", "")).strip()
        key_path = str(value.get("path", "")).strip()
        if not key_id or not key_path:
            continue
        keys[key_id] = SshPrivateKey(
            key_id=key_id,
            name=str(value.get("name", "")).strip() or Path(key_path).name,
            path=key_path,
        )
    return keys


def _write_ssh_private_keys(
    keys: Dict[str, SshPrivateKey],
    path: Union[str, Path],
) -> None:
    """原子写入 SSH 私钥库。"""
    key_file = Path(path)
    key_file.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = key_file.with_suffix(f"{key_file.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(
            {"ssh_private_keys": [asdict(key) for key in keys.values()]},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(key_file)


def import_ssh_private_key(
    private_key_path: Union[str, Path],
    path: Union[str, Path] = SSH_PRIVATE_KEYS_FILE,
) -> SshPrivateKey:
    """登记私钥路径，不复制或读取私钥内容。"""
    selected_path = Path(private_key_path).expanduser()
    if not selected_path.is_file():
        raise ValueError("SSH 私钥文件不存在")
    normalized_path = str(selected_path.resolve())
    keys = load_ssh_private_keys(path)
    for key in keys.values():
        if str(Path(key.path)).casefold() == normalized_path.casefold():
            return key
    key = SshPrivateKey(
        key_id=uuid.uuid4().hex,
        name=selected_path.name,
        path=normalized_path,
    )
    keys[key.key_id] = key
    _write_ssh_private_keys(keys, path)
    return key


def remove_ssh_private_key(
    key_id: str,
    path: Union[str, Path] = SSH_PRIVATE_KEYS_FILE,
) -> None:
    """移除私钥记录，不删除原始文件。"""
    keys = load_ssh_private_keys(path)
    if key_id not in keys:
        raise ValueError("所选 SSH 私钥不存在")
    del keys[key_id]
    _write_ssh_private_keys(keys, path)


def resolve_private_key_path(
    connection: DatabaseConnectionConfig,
    private_keys: Dict[str, SshPrivateKey] | None = None,
) -> str:
    """解析私钥库中的文件路径。"""
    if not connection.ssh_private_key_id:
        raise ValueError("请从 SSH 私钥库选择私钥")
    keys = private_keys if private_keys is not None else load_ssh_private_keys()
    key = keys.get(connection.ssh_private_key_id)
    if key is None:
        raise ValueError("当前环境引用的 SSH 私钥已不存在，请重新选择")
    return key.path


def load_database_connections(
    path: Union[str, Path] = DATABASE_CONNECTIONS_FILE,
) -> Dict[str, DatabaseConnectionConfig]:
    """加载所有环境配置，损坏数据使用默认值。"""
    connections = _default_connections()
    config_path = Path(path)
    if not config_path.exists():
        return connections
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return connections
    if not isinstance(data, dict):
        return connections
    scoped = data.get("database_connections_by_environment")
    if not isinstance(scoped, dict):
        return connections
    for environment in SUPPORTED_ENVIRONMENTS:
        connections[environment] = DatabaseConnectionConfig.from_mapping(
            scoped.get(environment)
        )
    return connections


def save_database_connection(
    environment: str,
    connection: DatabaseConnectionConfig,
    path: Union[str, Path] = DATABASE_CONNECTIONS_FILE,
) -> DatabaseConnectionConfig:
    """保存单个环境，不修改其他环境。"""
    if environment not in SUPPORTED_ENVIRONMENTS:
        raise ValueError(f"不支持的环境：{environment}")
    validate_database_connection(connection)
    connections = load_database_connections(path)
    connections[environment] = connection
    config_path = Path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = config_path.with_suffix(f"{config_path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(
            {
                "database_connections_by_environment": {
                    name: asdict(config)
                    for name, config in connections.items()
                }
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(config_path)
    return connection


def validate_database_connection(
    connection: DatabaseConnectionConfig,
) -> None:
    """校验完整的 SSH 和 MySQL 配置。"""
    required = (
        (connection.ssh_host, "SSH 主机不能为空"),
        (connection.ssh_username, "SSH 用户名不能为空"),
        (connection.database_host, "数据库主机不能为空"),
        (connection.database_name, "数据库名称不能为空"),
        (connection.database_username, "数据库用户名不能为空"),
    )
    for value, message in required:
        if not str(value).strip():
            raise ValueError(message)
    for port, label in (
        (connection.ssh_port, "SSH 端口"),
        (connection.database_port, "数据库端口"),
    ):
        if not 1 <= int(port) <= 65535:
            raise ValueError(f"{label}必须在 1 到 65535 之间")
    private_key_path = resolve_private_key_path(connection)
    if not Path(private_key_path).is_file():
        raise ValueError("SSH 私钥文件不存在，请重新导入")


def is_database_connection_configured(
    connection: DatabaseConnectionConfig,
) -> bool:
    """判断环境是否拥有完整可用的本地配置。"""
    try:
        validate_database_connection(connection)
    except (TypeError, ValueError):
        return False
    return True


def _connect_ssh_client(connection: DatabaseConnectionConfig):
    """仅使用选中的私钥建立 SSH 会话。"""
    try:
        import paramiko
    except ImportError as error:  # pragma: no cover - depends on installation
        raise RuntimeError("缺少 Paramiko，请先安装项目依赖") from error

    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    private_key_path = resolve_private_key_path(connection)
    client.connect(
        hostname=connection.ssh_host,
        port=connection.ssh_port,
        username=connection.ssh_username,
        key_filename=private_key_path,
        password=None,
        allow_agent=False,
        look_for_keys=False,
        timeout=10,
        banner_timeout=10,
        auth_timeout=10,
    )
    return client


class _ForwardServer(socketserver.ThreadingTCPServer):
    """SSH 端口转发使用的本地线程服务器。"""

    allow_reuse_address = True
    daemon_threads = True


def _forward_handler(transport, remote_address):
    """创建经 SSH 转发流量的套接字处理器。"""

    class ForwardHandler(socketserver.BaseRequestHandler):
        """通过 SSH 转发一个本地连接。"""

        def handle(self) -> None:
            """在本地套接字和 SSH 通道间转发数据。"""
            channel = transport.open_channel(
                "direct-tcpip",
                remote_address,
                self.request.getpeername(),
            )
            if channel is None:
                return
            try:
                while True:
                    readable, _, _ = select.select([self.request, channel], [], [])
                    if self.request in readable:
                        data = self.request.recv(32768)
                        if not data:
                            break
                        channel.sendall(data)
                    if channel in readable:
                        data = channel.recv(32768)
                        if not data:
                            break
                        self.request.sendall(data)
            finally:
                channel.close()

    return ForwardHandler


@contextmanager
def _ssh_tunnel(connection: DatabaseConnectionConfig) -> Iterator[int]:
    """把远程数据库映射到临时本地端口。"""
    client = _connect_ssh_client(connection)
    server = None
    try:
        transport = client.get_transport()
        if transport is None or not transport.is_active():
            raise ConnectionError("SSH 连接未建立")
        server = _ForwardServer(
            ("127.0.0.1", 0),
            _forward_handler(
                transport,
                (connection.database_host, connection.database_port),
            ),
        )
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        yield int(server.server_address[1])
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        client.close()


@contextmanager
def open_database_connection(
    connection: DatabaseConnectionConfig,
):
    """通过私钥 SSH 隧道打开 MySQL 连接。"""
    validate_database_connection(connection)
    try:
        import pymysql
    except ImportError as error:  # pragma: no cover - depends on installation
        raise RuntimeError("缺少 PyMySQL，请先安装项目依赖") from error

    with _ssh_tunnel(connection) as local_port:
        database = pymysql.connect(
            host="127.0.0.1",
            port=local_port,
            user=connection.database_username,
            password=connection.database_password,
            database=connection.database_name,
            charset=connection.database_charset,
            connect_timeout=10,
            read_timeout=10,
            write_timeout=10,
            autocommit=False,
        )
        try:
            yield database
        finally:
            database.close()


def test_database_connection(connection: DatabaseConnectionConfig) -> str:
    """建立隧道并执行只读查询测试连接。"""
    started = time.perf_counter()
    with open_database_connection(connection) as database:
        with database.cursor() as cursor:
            cursor.execute("SELECT VERSION()")
            row = cursor.fetchone()
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    version = str(row[0]) if row else "unknown"
    return f"连接成功 · MySQL {version} · {elapsed_ms} ms"
