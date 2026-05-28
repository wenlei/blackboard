import tempfile
from pathlib import Path

import pytest

from blackboard.archive.archiver import Archiver, LocalNasStorage


@pytest.fixture
def session_data():
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir)
        ses_dir = data_dir / "test-archive"
        ses_dir.mkdir(parents=True)
        (ses_dir / "config.json").write_text('{"test":true}')
        (ses_dir / "strategy.psc").write_text("WORKFLOW: test")
        (ses_dir / "conversation.log").write_text("[2024-01-01] [user] hello")
        yield data_dir


@pytest.fixture
def remote_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


class TestArchive:
    def test_archive_local_nas(self, session_data, remote_dir):
        archiver = Archiver(data_dir=str(session_data))
        result = archiver.archive("test-archive", "local_nas", remote_dir)

        archive_path = Path(remote_dir) / "test-archive.tar.gz"
        assert archive_path.exists()
        assert "test-archive.tar.gz" in result

        ses_dir = session_data / "test-archive"
        assert (ses_dir / "config.json").exists()
        assert (ses_dir / "strategy.psc").exists()
        assert not (ses_dir / "conversation.log").exists()

    def test_archive_nonexistent_session(self, session_data, remote_dir):
        archiver = Archiver(data_dir=str(session_data))
        with pytest.raises(FileNotFoundError, match="not found"):
            archiver.archive("ghost-session", "local_nas", remote_dir)

    def test_archive_log_written(self, session_data, remote_dir):
        archiver = Archiver(data_dir=str(session_data))
        archiver.archive("test-archive", "local_nas", remote_dir)

        log_path = Path(remote_dir) / "log.md"
        assert log_path.exists()
        content = log_path.read_text()
        assert "test-archive" in content

    def test_storage_backend_local_nas(self):
        nas = LocalNasStorage()
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "source.txt"
            src.write_text("hello")
            dest = Path(tmpdir) / "sub" / "dest.txt"
            result = nas.upload(str(src), str(dest))
            assert Path(result).exists()

    def test_check_disk_usage(self, session_data):
        archiver = Archiver(data_dir=str(session_data))
        usage, _ = archiver.check_disk_usage()
        assert usage > 0

    def test_check_disk_usage_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            archiver = Archiver(data_dir=tmpdir)
            usage, _ = archiver.check_disk_usage()
            assert usage == 0

    def test_check_disk_usage_nonexistent(self):
        archiver = Archiver(data_dir="/tmp/blackboard-nonexistent-12345")
        usage, _ = archiver.check_disk_usage()
        assert usage == 0

    def test_archive_cleans_files_except_config_strategy(self, session_data, remote_dir):
        ses_dir = session_data / "test-archive"
        (ses_dir / "extra_file.txt").write_text("extra")
        (ses_dir / "agents").mkdir(exist_ok=True)
        (ses_dir / "agents" / "agent_mem.md").write_text("memory")

        archiver = Archiver(data_dir=str(session_data))
        archiver.archive("test-archive", "local_nas", remote_dir)

        assert (ses_dir / "config.json").exists()
        assert (ses_dir / "strategy.psc").exists()
        assert not (ses_dir / "extra_file.txt").exists()
        assert not (ses_dir / "agents").exists()

    def test_archive_with_trailing_slash(self, session_data, remote_dir):
        archiver = Archiver(data_dir=str(session_data))
        result = archiver.archive("test-archive", "local_nas", remote_dir + "/")
        archive_path = Path(remote_dir) / "test-archive.tar.gz"
        assert archive_path.exists()

    def test_local_nas_download(self, session_data, remote_dir):
        archiver = Archiver(data_dir=str(session_data))
        archiver.archive("test-archive", "local_nas", remote_dir)

        nas = LocalNasStorage()
        archive_path = Path(remote_dir) / "test-archive.tar.gz"
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "restored.tar.gz"
            result = nas.download(str(archive_path), str(dest))
            assert dest.exists()
            assert "restored" in result

    def test_local_nas_mkdir_on_upload(self):
        nas = LocalNasStorage()
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "src.txt"
            src.write_text("data")
            dest = Path(tmpdir) / "deep" / "nested" / "file.txt"
            result = nas.upload(str(src), str(dest))
            assert Path(result).exists()

    def test_s3_parse_path(self):
        from blackboard.archive.archiver import S3Storage
        bucket, key = S3Storage._parse_s3_path("s3://my-bucket/path/to/file.tar.gz")
        assert bucket == "my-bucket"
        assert key == "path/to/file.tar.gz"

    def test_s3_parse_path_no_key(self):
        from blackboard.archive.archiver import S3Storage
        bucket, key = S3Storage._parse_s3_path("s3://my-bucket")
        assert bucket == "my-bucket"
        assert key == ""

    def test_storage_backend_registry(self):
        from blackboard.archive.archiver import STORAGE_BACKENDS, S3Storage, SftpStorage, LocalNasStorage
        assert STORAGE_BACKENDS["local_nas"] == LocalNasStorage
        assert STORAGE_BACKENDS["s3"] == S3Storage
        assert STORAGE_BACKENDS["sftp"] == SftpStorage

    def test_archive_unknown_storage_type(self, session_data, remote_dir):
        archiver = Archiver(data_dir=str(session_data))
        result = archiver.archive("test-archive", "unknown_type_xyz", remote_dir)
        assert "test-archive.tar.gz" in result
