from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class User:
    id: str
    username: str
    password_hash: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
