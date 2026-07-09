from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.hybrid_search import router


class FakeSearchClient:
    def health_check(self) -> bool:
        return True

    def search_unified(self, **kwargs):
        return {
            "total": 1,
            "hits": [
                {
                    "score": 1.0,
                    "chunk_text": "Blur node documentation",
                    "chunk_id": "blur-1",
                    "section_name": "Blur",
                    "url": "https://learn.foundry.com/nuke/blur",
                    "nuke_node_name": "Blur",
                    "section": "Filter",
                }
            ],
        }


class FakeEmbeddingsService:
    async def embed_query(self, query: str):
        return [0.1, 0.2, 0.3]


def make_client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.state.search_client = FakeSearchClient()
    app.state.embeddings_service = FakeEmbeddingsService()
    return TestClient(app)


def test_hybrid_search_accepts_no_slash_without_redirect():
    client = make_client()

    response = client.post(
        "/api/v1/hybrid-search",
        json={"query": "Blur node", "size": 5, "use_hybrid": True, "knowledge_source": "nuke"},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert response.json()["hits"][0]["nuke_node_name"] == "Blur"


def test_hybrid_search_accepts_trailing_slash():
    client = make_client()

    response = client.post(
        "/api/v1/hybrid-search/",
        json={"query": "Blur node", "size": 5, "use_hybrid": True, "knowledge_source": "nuke"},
        follow_redirects=False,
    )

    assert response.status_code == 200
