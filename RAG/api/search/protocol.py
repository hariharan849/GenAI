from typing import Any, Dict, List, Optional, Protocol


class SearchClient(Protocol):
    backend_name: str

    def health_check(self) -> bool: ...

    def get_index_stats(self) -> Dict[str, Any]: ...

    def setup_indices(self, force: bool = False) -> Dict[str, bool]: ...

    def search_unified(
        self,
        query: str,
        query_embedding: Optional[List[float]] = None,
        size: int = 10,
        from_: int = 0,
        categories: Optional[List[str]] = None,
        latest: bool = False,
        use_hybrid: bool = True,
        min_score: float = 0.0,
        knowledge_source: str = "nuke",
    ) -> Dict[str, Any]: ...

    def bulk_index_chunks(self, chunks: List[Dict[str, Any]]) -> Dict[str, int]: ...
