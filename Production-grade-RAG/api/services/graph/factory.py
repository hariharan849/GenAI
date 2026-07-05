import logging
from typing import Optional

from api.config import get_settings

logger = logging.getLogger(__name__)


def make_neo4j_client():
    """Return a Neo4jClient if Neo4j is enabled in settings, else None."""
    settings = get_settings()
    cfg = settings.neo4j
    if not cfg.enabled:
        logger.info("Neo4j disabled (NEO4J__ENABLED=false) — KG retrieval skipped")
        return None
    try:
        from .client import Neo4jClient
        client = Neo4jClient(bolt_url=cfg.bolt_url, user=cfg.user, password=cfg.password)
    except ImportError:
        logger.warning("neo4j package not installed — KG retrieval disabled. Run: uv add neo4j")
        return None
    logger.info(f"Neo4j enabled — connecting to {cfg.bolt_url}")
    return client
