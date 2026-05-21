import psutil

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

class HealthCheckResponse(BaseModel):
    status: str
    cpu_percent: float
    memory_percent: float

@router.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """Health check endpoint that returns the status of the server along with CPU and memory usage."""
    cpu_percent = psutil.cpu_percent(interval=1)
    memory_percent = psutil.virtual_memory().percent
    return HealthCheckResponse(status="ok", cpu_percent=cpu_percent, memory_percent=memory_percent)
