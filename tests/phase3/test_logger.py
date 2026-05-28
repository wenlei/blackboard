

from blackboard.logger.session_logger import SessionLogger


class TestSessionLogger:
    def test_ensure_dir(self, tmp_path):
        sl = SessionLogger("test-s1", str(tmp_path))
        sl.ensure_dir()
        assert (tmp_path / "test-s1").is_dir()

    def test_log_and_read_conversation(self, tmp_path):
        sl = SessionLogger("test-s1", str(tmp_path))
        sl.log_conversation("user", "hello world")
        sl.log_conversation("assistant", "hi there")

        content = sl.read_conversation()
        assert "[user] hello world" in content
        assert "[assistant] hi there" in content

    def test_log_and_read_messages(self, tmp_path):
        sl = SessionLogger("test-s1", str(tmp_path))
        sl.log_message("inbox", {"type": "chat", "content": "hello"})
        sl.log_message("outbox", {"type": "response", "content": "hi"})

        msgs = sl.read_messages()
        assert len(msgs) == 2
        assert msgs[0]["stream"] == "inbox"
        assert msgs[0]["payload"]["type"] == "chat"
        assert "timestamp" in msgs[0]
        assert msgs[1]["stream"] == "outbox"

    def test_log_and_read_events(self, tmp_path):
        sl = SessionLogger("test-s1", str(tmp_path))
        sl.log_event("session_created", {"agent_count": 2})
        sl.log_event("session_paused", {})

        events = sl.read_events()
        assert len(events) == 2
        assert events[0]["type"] == "session_created"
        assert events[0]["data"]["agent_count"] == 2
        assert "timestamp" in events[0]
        assert events[1]["type"] == "session_paused"

    def test_read_empty_conversation(self, tmp_path):
        sl = SessionLogger("nonexistent", str(tmp_path))
        assert sl.read_conversation() == ""

    def test_read_empty_messages(self, tmp_path):
        sl = SessionLogger("nonexistent", str(tmp_path))
        assert sl.read_messages() == []

    def test_read_empty_events(self, tmp_path):
        sl = SessionLogger("nonexistent", str(tmp_path))
        assert sl.read_events() == []

    def test_read_config(self, tmp_path):
        sl = SessionLogger("test-s1", str(tmp_path))
        sl.ensure_dir()
        (sl.dir / "config.json").write_text('{"session_id":"test-s1","agents":[]}')

        config = sl.read_config()
        assert config["session_id"] == "test-s1"
        assert config["agents"] == []

    def test_read_config_missing(self, tmp_path):
        sl = SessionLogger("nonexistent", str(tmp_path))
        assert sl.read_config() == {}

    def test_read_write_strategy(self, tmp_path):
        sl = SessionLogger("test-s1", str(tmp_path))
        sl.ensure_dir()
        psc = "ARCHITECT: 设计方案\nPROGRAMMER: 编写代码"
        (sl.dir / "strategy.psc").write_text(psc)

        assert sl.read_strategy() == psc

    def test_read_strategy_missing(self, tmp_path):
        sl = SessionLogger("nonexistent", str(tmp_path))
        assert sl.read_strategy() == ""

    def test_multiple_events_accumulate(self, tmp_path):
        sl = SessionLogger("test-s1", str(tmp_path))
        for i in range(5):
            sl.log_event(f"event_{i}", {"index": i})

        events = sl.read_events()
        assert len(events) == 5
        assert events[0]["type"] == "event_0"
        assert events[4]["type"] == "event_4"

    def test_messages_preserve_unicode(self, tmp_path):
        sl = SessionLogger("test-s1", str(tmp_path))
        sl.log_message("inbox", {"type": "chat", "content": "你好世界"})

        msgs = sl.read_messages()
        assert msgs[0]["payload"]["content"] == "你好世界"
