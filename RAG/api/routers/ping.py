from fastapi import APIRouter
from sqlalchemy import text

from ..dependencies import DatabaseDep, SearchDep, SettingsDep
from ..metrics import SERVICE_HEALTH
from ..schemas.api.health import HealthResponse, ServiceStatus
from ..services.ollama import OllamaClient

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check(settings: SettingsDep, database: DatabaseDep, search_client: SearchDep) -> HealthResponse:
    """Comprehensive health check endpoint for monitoring and load balancer probes.

    :returns: Service health status with version and connectivity checks
    :rtype: HealthResponse
    """
    services = {}
    overall_status = "ok"

    def _check_service(name: str, check_func, *args, **kwargs):
        """Helper to standardize service health checks."""
        try:
            if kwargs.get("is_async"):
                # Handle async functions separately in the calling code
                return check_func(*args)
            result = check_func(*args)
            services[name] = result
            if result.status != "healthy":
                nonlocal overall_status
                overall_status = "degraded"
        except Exception as e:
            services[name] = ServiceStatus(status="unhealthy", message=str(e))
            overall_status = "degraded"

    # Database check
    def _check_database():
        with database.get_session() as session:
            session.execute(text("SELECT 1"))
        return ServiceStatus(status="healthy", message="Connected successfully")

    # Search backend check
    def _check_search():
        if not search_client.health_check():
            return ServiceStatus(status="unhealthy", message="Not responding")
        stats = search_client.get_index_stats()
        readiness = ""
        if search_client.backend_name == "postgres_embedding":
            readiness = (
                f", extension_ready={stats.get('extension_ready', False)}, "
                f"schema_ready={stats.get('schema_ready', False)}"
            )
        return ServiceStatus(
            status="healthy",
            message=(
                f"backend={search_client.backend_name}, index '{stats.get('index_name', 'unknown')}' "
                f"with {stats.get('document_count', 0)} chunks{readiness}"
            ),
        )

    # Run synchronous checks
    _check_service("database", _check_database)
    _check_service("search", _check_search)

    # Handle Ollama async check separately
    try:
        ollama_client = OllamaClient(settings)
        ollama_health = await ollama_client.health_check()
        services["ollama"] = ServiceStatus(status=ollama_health["status"], message=ollama_health["message"])
        if ollama_health["status"] != "healthy":
            overall_status = "degraded"
    except Exception as e:
        services["ollama"] = ServiceStatus(status="unhealthy", message=str(e))
        overall_status = "degraded"

    # Update Prometheus service health gauges
    SERVICE_HEALTH.labels(service="database").set(1 if services.get("database", ServiceStatus(status="unhealthy")).status == "healthy" else 0)
    SERVICE_HEALTH.labels(service="search").set(1 if services.get("search", ServiceStatus(status="unhealthy")).status == "healthy" else 0)
    SERVICE_HEALTH.labels(service="ollama").set(1 if services.get("ollama", ServiceStatus(status="unhealthy")).status == "healthy" else 0)

    return HealthResponse(
        status=overall_status,
        version=settings.app_version,
        environment=settings.environment,
        service_name=settings.service_name,
        services=services,
    )
