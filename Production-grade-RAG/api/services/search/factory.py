"""Compatibility shim for search backend factories."""

from typing import Optional

from api.config import Settings
from api.search.factory import make_search_client as _make_search_client
from api.search.factory import make_search_client_fresh as _make_search_client_fresh


def make_search_client(settings: Optional[Settings] = None):
    return _make_search_client(settings)


def make_search_client_fresh(settings: Optional[Settings] = None, host: Optional[str] = None):
    return _make_search_client_fresh(settings, host=host)
