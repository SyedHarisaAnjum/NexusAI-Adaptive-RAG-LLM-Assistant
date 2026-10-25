import json
import re
import threading
import uuid
from pathlib import Path

from app.config import get_settings
from app.schemas import ChatMessage

# Session ids are server-generated uuid4 hex strings. Anything else is rejected
# before it gets near the filesystem.
SESSION_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


class SessionStore:
    """Persists each conversation as data/sessions/<session_id>.json:
    {"owner_id": "...", "messages": [...]}.

    A session owned by another user is treated as not found.
    """

    def __init__(self) -> None:
        self._dir = get_settings().sessions_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, session_id: str) -> Path | None:
        if not SESSION_ID_PATTERN.fullmatch(session_id):
            return None
        return self._dir / f"{session_id}.json"

    def _read(self, path: Path) -> dict | None:
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        # Sessions from before authentication existed have no owner: never served.
        return data if isinstance(data, dict) else None

    def _write(self, path: Path, data: dict) -> None:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(path)

    def create(self, owner_id: str) -> str:
        session_id = uuid.uuid4().hex
        with self._lock:
            self._write(self._path(session_id), {"owner_id": owner_id, "messages": []})
        return session_id

    def get_messages(self, session_id: str, owner_id: str) -> list[ChatMessage] | None:
        path = self._path(session_id)
        if path is None:
            return None
        with self._lock:
            data = self._read(path)
        if data is None or data.get("owner_id") != owner_id:
            return None
        return [ChatMessage(**m) for m in data["messages"]]

    def append(self, session_id: str, owner_id: str, messages: list[ChatMessage]) -> None:
        path = self._path(session_id)
        if path is None:
            raise ValueError("Invalid session id")
        with self._lock:
            data = self._read(path) or {"owner_id": owner_id, "messages": []}
            if data.get("owner_id") != owner_id:
                raise PermissionError("Session belongs to another user")
            data["messages"].extend(m.model_dump(mode="json") for m in messages)
            self._write(path, data)

    def delete(self, session_id: str, owner_id: str) -> bool:
        path = self._path(session_id)
        if path is None:
            return False
        with self._lock:
            data = self._read(path)
            if data is None or data.get("owner_id") != owner_id:
                return False
            path.unlink()
        return True


session_store = SessionStore()
