from typing import Protocol

import aiomysql

from app.models.user import User


class UserRepository(Protocol):
    async def insert(self, user: User) -> User:
        raise NotImplementedError

    async def get_by_username(self, username: str) -> User | None:
        raise NotImplementedError

    async def get_by_id(self, user_id: str) -> User | None:
        raise NotImplementedError


class MySQLUserRepository:
    def __init__(self, connection: aiomysql.Connection):
        self.connection = connection

    async def insert(self, user: User) -> User:
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO users (id, username, password_hash, is_active, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (user.id, user.username, user.password_hash, user.is_active, user.created_at, user.updated_at),
            )
        await self.connection.commit()
        return user

    async def get_by_username(self, username: str) -> User | None:
        async with self.connection.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(
                """
                SELECT id, username, password_hash, is_active, created_at, updated_at
                FROM users
                WHERE username = %s
                LIMIT 1
                """,
                (username,),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return User(
            id=str(row["id"]),
            username=str(row["username"]),
            password_hash=None if row["password_hash"] is None else str(row["password_hash"]),
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def get_by_id(self, user_id: str) -> User | None:
        async with self.connection.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(
                """
                SELECT id, username, password_hash, is_active, created_at, updated_at
                FROM users
                WHERE id = %s
                LIMIT 1
                """,
                (user_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return User(
            id=str(row["id"]),
            username=str(row["username"]),
            password_hash=None if row["password_hash"] is None else str(row["password_hash"]),
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
