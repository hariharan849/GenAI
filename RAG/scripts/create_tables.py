"""Create all database tables from the SQLAlchemy ORM models.

Run once against a fresh database (or after adding new models):

    uv run python scripts/create_tables.py

Idempotent — skips tables that already exist.
"""

import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    from api.config import get_settings
    from api.db.interfaces.postgresql import Base, ensure_nuke_page_kg_columns
    from api.schemas.database.config import PostgreSQLSettings
    from sqlalchemy import create_engine, inspect

    # Import all models so they register with Base.metadata before create_all
    import api.models.nuke_page  # noqa: F401
    import api.models.rag_interaction  # noqa: F401

    settings = get_settings()
    config = PostgreSQLSettings(
        database_url=settings.postgres_database_url,
        echo_sql=False,
    )

    engine = create_engine(config.database_url, pool_pre_ping=True)
    inspector = inspect(engine)
    before = set(inspector.get_table_names())

    Base.metadata.create_all(bind=engine)
    ensure_nuke_page_kg_columns(engine)

    after = set(inspector.get_table_names())
    created = after - before
    if created:
        logger.info(f"Created tables: {', '.join(sorted(created))}")
    else:
        logger.info("All tables already exist — nothing created")

    engine.dispose()


if __name__ == "__main__":
    main()
