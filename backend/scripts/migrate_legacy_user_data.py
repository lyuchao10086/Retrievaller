"""Transfer legacy default_user data to one registered user without stale vectors.

This administrator-only development migration deliberately removes legacy
chunks and Milvus vectors, then resets transferred documents to ``uploaded``.
The target account must process the documents again under its own user ID.
"""

import argparse
import asyncio
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_settings
from app.core.database import get_database_pool, init_database
from app.repositories.user import MySQLUserRepository
from app.services.knowledge_base import DEFAULT_USER_ID
from app.services.vector_service import MilvusVectorService


async def migrate_legacy_user_data(target_username: str, source_user_id: str) -> int:
    """Move one legacy user's metadata and remove incompatible vector indexes.

    Database writes use one transaction. Vector cleanup is performed first and
    is idempotent, so a failed run can be safely repeated.
    """
    settings = get_settings()
    await init_database()
    pool = await get_database_pool()
    async with pool.acquire() as connection:
        target_user = await MySQLUserRepository(connection).get_by_username(target_username)
        if target_user is None or not target_user.is_active:
            print("Target user does not exist or is inactive.")
            return 2

        async with connection.cursor() as cursor:
            await cursor.execute(
                "SELECT id FROM knowledge_bases WHERE user_id = %s",
                (source_user_id,),
            )
            knowledge_base_ids = [str(row[0]) for row in await cursor.fetchall()]

        if not knowledge_base_ids:
            print("No legacy knowledge bases found; nothing to migrate.")
            await connection.rollback()
            return 0

        vector_service = MilvusVectorService(
            host=settings.milvus_host,
            port=settings.milvus_port,
            collection_name=settings.milvus_collection_document_chunks,
            embedding_dimension=settings.embedding_dimension,
        )
        for kb_id in knowledge_base_ids:
            vector_service.delete_chunk_embeddings_by_knowledge_base(source_user_id, kb_id)

        try:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    DELETE FROM chunks
                    WHERE user_id = %s
                      AND knowledge_base_id IN (
                          SELECT id FROM knowledge_bases WHERE user_id = %s
                      )
                    """,
                    (source_user_id, source_user_id),
                )
                await cursor.execute(
                    """
                    UPDATE documents
                    SET user_id = %s,
                        status = 'uploaded',
                        error_message = NULL,
                        parsed_bucket = NULL,
                        parsed_object_key = NULL,
                        task_id = NULL
                    WHERE user_id = %s
                    """,
                    (target_user.id, source_user_id),
                )
                await cursor.execute(
                    "UPDATE knowledge_bases SET user_id = %s WHERE user_id = %s",
                    (target_user.id, source_user_id),
                )
                await cursor.execute(
                    "UPDATE qa_records SET user_id = %s WHERE user_id = %s",
                    (target_user.id, source_user_id),
                )
                await cursor.execute(
                    "UPDATE evaluations SET user_id = %s WHERE user_id = %s",
                    (target_user.id, source_user_id),
                )
            await connection.commit()
        except Exception:
            await connection.rollback()
            raise

    print(
        "Migrated %d knowledge base(s) to %s. Documents must be processed again."
        % (len(knowledge_base_ids), target_username)
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate legacy user data to a registered account.")
    parser.add_argument("--to-username", required=True, help="Existing active account that will own the data")
    parser.add_argument("--from-user-id", default=DEFAULT_USER_ID, help="Legacy owner ID; defaults to default_user")
    parser.add_argument("--confirm", action="store_true", help="Required acknowledgement before modifying data")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.confirm:
        print("Refusing to modify data without --confirm.")
        return 2
    return asyncio.run(migrate_legacy_user_data(args.to_username, args.from_user_id))


if __name__ == "__main__":
    raise SystemExit(main())
