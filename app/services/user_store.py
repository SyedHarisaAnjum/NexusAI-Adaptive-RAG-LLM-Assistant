import json
import threading
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel

from app.config import get_settings


class User(BaseModel):
    user_id: str
    email: str
    password_hash: str
    created_at: datetime


class EmailAlreadyRegisteredError(ValueError):
    pass


class UserStore:
    """Stores accounts in data/users.json. Passwords are only ever stored hashed."""

    def __init__(self) -> None:
        self._file = get_settings().users_file
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _read_all(self) -> dict[str, dict]:
        if not self._file.exists():
            return {}
        return json.loads(self._file.read_text(encoding="utf-8"))

    def _write_all(self, records: dict[str, dict]) -> None:
        tmp = self._file.with_suffix(".tmp")
        tmp.write_text(json.dumps(records, indent=2), encoding="utf-8")
        tmp.replace(self._file)

    @staticmethod
    def normalize_email(email: str) -> str:
        return email.strip().lower()

    def get(self, user_id: str) -> User | None:
        with self._lock:
            record = self._read_all().get(user_id)
        return User(**record) if record else None

    def get_by_email(self, email: str) -> User | None:
        email = self.normalize_email(email)
        with self._lock:
            records = self._read_all()
        for record in records.values():
            if record["email"] == email:
                return User(**record)
        return None

    def create(self, email: str, password_hash: str) -> User:
        email = self.normalize_email(email)
        with self._lock:
            records = self._read_all()
            if any(r["email"] == email for r in records.values()):
                raise EmailAlreadyRegisteredError(email)
            user = User(
                user_id=uuid.uuid4().hex,
                email=email,
                password_hash=password_hash,
                created_at=datetime.now(timezone.utc),
            )
            records[user.user_id] = user.model_dump(mode="json")
            self._write_all(records)
        return user


user_store = UserStore()
