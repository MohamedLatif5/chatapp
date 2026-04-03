from fastapi import FastAPI

from app.api.v1 import health

app = FastAPI(
    title="ChatApp API",
    version="0.1.0",
    description="Real-time chat backend: FastAPI + WebSockets + Redis + PostgreSQL",
)

app.include_router(health.router, prefix="/api/v1")
