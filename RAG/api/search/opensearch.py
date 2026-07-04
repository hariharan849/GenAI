"""OpenSearch search backend exports."""

from api.services.opensearch.client import OpenSearchClient
from api.services.opensearch.factory import make_opensearch_client, make_opensearch_client_fresh

__all__ = ["OpenSearchClient", "make_opensearch_client", "make_opensearch_client_fresh"]
