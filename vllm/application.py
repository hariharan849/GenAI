
import uvicorn
from src.vllm_serve.config import Settings
from src.vllm_serve.main import app

def main():
    settings = Settings()
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
