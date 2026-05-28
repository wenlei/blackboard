import shutil
import tarfile
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path


class RemoteStorage(ABC):
    @abstractmethod
    def upload(self, local_path: str, remote_path: str) -> str: ...
    @abstractmethod
    def download(self, remote_path: str, local_path: str) -> str: ...
    @abstractmethod
    def write_log(self, remote_path: str, content: str): ...


class LocalNasStorage(RemoteStorage):
    def upload(self, local_path: str, remote_path: str) -> str:
        dest = Path(remote_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, dest)
        return str(dest)

    def download(self, remote_path: str, local_path: str) -> str:
        dest = Path(local_path)
        shutil.copy2(remote_path, dest)
        return str(dest)

    def write_log(self, remote_path: str, content: str):
        log_path = Path(remote_path).parent / "log.md"
        with open(log_path, "a") as f:
            f.write(content + "\n")


class S3Storage(RemoteStorage):
    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None:
            import boto3
            self._client = boto3.client("s3")
        return self._client

    def upload(self, local_path: str, remote_path: str) -> str:
        s3 = self._get_client()
        bucket, key = self._parse_s3_path(remote_path)
        s3.upload_file(local_path, bucket, key)
        return remote_path

    def download(self, remote_path: str, local_path: str) -> str:
        s3 = self._get_client()
        bucket, key = self._parse_s3_path(remote_path)
        s3.download_file(bucket, key, local_path)
        return local_path

    def write_log(self, remote_path: str, content: str):
        bucket, key = self._parse_s3_path(remote_path)
        log_key = key.removesuffix(".tar.gz") + "_log.md"
        s3 = self._get_client()
        s3.put_object(Bucket=bucket, Key=log_key, Body=content)

    @staticmethod
    def _parse_s3_path(uri: str) -> tuple[str, str]:
        uri = uri.replace("s3://", "")
        parts = uri.split("/", 1)
        return parts[0], parts[1] if len(parts) > 1 else ""


class SftpStorage(RemoteStorage):
    def __init__(self, host: str = "localhost", port: int = 22,
                 username: str | None = None, password: str | None = None,
                 key_filename: str | None = None):
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._key_filename = key_filename
        self._client = None

    def _get_client(self):
        if self._client is None:
            import paramiko
            self._client = paramiko.SSHClient()
            self._client.set_missing_host_key_policy(paramiko.RejectPolicy())
            self._client.load_system_host_keys()
            self._client.connect(
                self._host, port=self._port,
                username=self._username, password=self._password,
                key_filename=self._key_filename,
            )
        return self._client

    def upload(self, local_path: str, remote_path: str) -> str:
        sftp = self._get_client().open_sftp()
        sftp.put(local_path, remote_path)
        sftp.close()
        return remote_path

    def download(self, remote_path: str, local_path: str) -> str:
        sftp = self._get_client().open_sftp()
        sftp.get(remote_path, local_path)
        sftp.close()
        return local_path

    def write_log(self, remote_path: str, content: str):
        sftp = self._get_client().open_sftp()
        log_path = remote_path.removesuffix(".tar.gz") + "_log.md"
        try:
            sftp.putfo(self._wrap_stringio(content), log_path)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("SFTP write_log failed: %s", e)
        finally:
            sftp.close()

    @staticmethod
    def _wrap_stringio(content: str):
        import io
        return io.BytesIO(content.encode())


STORAGE_BACKENDS: dict[str, type[RemoteStorage]] = {
    "local_nas": LocalNasStorage,
    "s3": S3Storage,
    "sftp": SftpStorage,
}


class Archiver:
    def __init__(self, data_dir: str = "/tmp/blackboard-sessions"):
        self.data_dir = Path(data_dir)

    def archive(self, session_id: str, remote_type: str, remote_path: str) -> str:
        ses_dir = self.data_dir / session_id
        if not ses_dir.exists():
            raise FileNotFoundError(f"Session {session_id} not found")

        archive_dir = Path(tempfile.mkdtemp())
        archive_file = archive_dir / f"{session_id}.tar.gz"

        with tarfile.open(archive_file, "w:gz") as tar:
            tar.add(str(ses_dir), arcname=session_id)

        backend_cls = STORAGE_BACKENDS.get(remote_type, LocalNasStorage)
        backend = backend_cls()
        dest_path = f"{remote_path.rstrip('/')}/{session_id}.tar.gz"
        result = backend.upload(str(archive_file), dest_path)

        from datetime import datetime, timezone
        log_entry = f"## {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} — Session {session_id} archived\n" \
                     f"- remote_type: {remote_type}\n- remote_path: {dest_path}"
        backend.write_log(dest_path, log_entry)

        for item in list(ses_dir.iterdir()):
            if item.name in ("config.json", "strategy.psc"):
                continue
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            else:
                item.unlink()

        shutil.rmtree(archive_dir, ignore_errors=True)
        return result

    def check_disk_usage(self) -> tuple[float, float]:
        total_bytes = 0
        if self.data_dir.exists():
            for f in self.data_dir.rglob("*"):
                if f.is_file():
                    total_bytes += f.stat().st_size
        return total_bytes, 0
