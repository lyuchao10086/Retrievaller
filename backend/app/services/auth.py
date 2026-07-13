from datetime import datetime, timezone
from uuid import uuid4

from app.core.security import hash_password, verify_password
from app.models.user import User
from app.repositories.user import UserRepository


class UsernameAlreadyExistsError(ValueError):
    pass


class InvalidCredentialsError(ValueError):
    pass


async def register_user(repository: UserRepository, username: str, password: str) -> User:
    if await repository.get_by_username(username) is not None:
        raise UsernameAlreadyExistsError("Username already exists")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    user = User(
        id=f"usr_{uuid4().hex}",
        username=username,
        password_hash=hash_password(password),
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    return await repository.insert(user)


async def authenticate_user(repository: UserRepository, username: str, password: str) -> User:
    user = await repository.get_by_username(username)
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        raise InvalidCredentialsError("Invalid username or password")
    return user
