from typing import Annotated

import aiomysql
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import Settings, get_settings
from app.core.database import get_db_connection
from app.core.security import create_access_token
from app.repositories.user import MySQLUserRepository, UserRepository
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.services.auth import (
    InvalidCredentialsError,
    UsernameAlreadyExistsError,
    authenticate_user,
    register_user,
)


router = APIRouter(prefix="/api/auth", tags=["auth"])


async def get_user_repository(
    connection: Annotated[aiomysql.Connection, Depends(get_db_connection)],
) -> UserRepository:
    return MySQLUserRepository(connection)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register_api(
    payload: RegisterRequest,
    repository: Annotated[UserRepository, Depends(get_user_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    try:
        user = await register_user(repository, payload.username, payload.password)
    except UsernameAlreadyExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists") from exc
    return _token_response(user.id, user.username, settings)


@router.post("/login", response_model=TokenResponse)
async def login_api(
    payload: LoginRequest,
    repository: Annotated[UserRepository, Depends(get_user_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    try:
        user = await authenticate_user(repository, payload.username, payload.password)
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password") from exc
    return _token_response(user.id, user.username, settings)


def _token_response(user_id: str, username: str, settings: Settings) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user_id, username),
        expires_in=settings.access_token_expire_minutes * 60,
        user_id=user_id,
        username=username,
    )
