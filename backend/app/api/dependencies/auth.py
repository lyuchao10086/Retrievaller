from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import TokenError, TokenExpiredError, decode_access_token
from app.core.database import get_database_pool
from app.core.logging import bind_log_context
from app.repositories.user import MySQLUserRepository


bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class CurrentUser:
    id: str
    username: str


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> CurrentUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = decode_access_token(credentials.credentials)
    except TokenExpiredError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired") from exc
    except TokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
    # Validate the bearer signature before touching MySQL so bad tokens do not
    # turn an authentication failure into a database availability failure.
    pool = await get_database_pool()
    async with pool.acquire() as connection:
        user = await MySQLUserRepository(connection).get_by_id(str(payload["sub"]))
        await connection.rollback()
    if user is None or not user.is_active or user.username != payload["username"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    bind_log_context(user_id=user.id)
    return CurrentUser(id=user.id, username=user.username)
