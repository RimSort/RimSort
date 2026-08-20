from pathlib import Path

from app.ai.chat_store import ChatStore


class TestChatStore:
    def test_roundtrip(self, tmp_path: Path) -> None:
        store = ChatStore(tmp_path / "chat.json")
        store.append("user", "hello")
        store.append("assistant", "hi")
        store.save()

        reloaded = ChatStore(tmp_path / "chat.json")
        assert len(reloaded.as_list()) == 2
        assert reloaded.as_list()[0]["content"] == "hello"
        assert "timestamp" in reloaded.as_list()[0]
