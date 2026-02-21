from firecrawl import FirecrawlApp
from src.config import settings

def get_firecrawl_client():
    return FirecrawlApp(api_key=settings.firecrawl.api_key)