import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.utils.app_info import AppInfo
from app.utils.json_utils import atomic_json_dump


class ChatStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (Path(AppInfo().app_storage_folder) / "ai_chat.json")
        self.messages: list[dict[str, str]] = []
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self.messages = []
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            raw = data.get("messages", [])
            if isinstance(raw, list):
                self.messages = []
                for m in raw:
                    if not isinstance(m, dict):
                        continue
                    entry: dict[str, str] = {
                        "role": str(m.get("role", "user")),
                        "content": str(m.get("content", "")),
                    }
                    timestamp = m.get("timestamp")
                    if timestamp:
                        entry["timestamp"] = str(timestamp)
                    self.messages.append(entry)
        except (json.JSONDecodeError, OSError):
            self.messages = []

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_json_dump({"messages": self.messages}, str(self.path), indent=2)

    def append(self, role: str, content: str, *, timestamp: str | None = None) -> None:
        entry: dict[str, str] = {
            "role": role,
            "content": content,
            "timestamp": timestamp or datetime.now().strftime("%H:%M:%S"),
        }
        self.messages.append(entry)

    def clear(self) -> None:
        self.messages = []
        self.save()

    def as_list(self) -> list[dict[str, str]]:
        return list(self.messages)
