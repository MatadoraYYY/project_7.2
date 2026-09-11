"""Application entry point. Run with: uvicorn app.main:app --reload"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import analytics, customers, offers
from app.core.config import get_settings
from app.core.database import init_db
from app.core.logging_config import configure_logging, get_logger
from app.models.schemas import HealthCheck

settings = get_settings()
configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Personal Promo Offers API in '%s' environment", settings.app_env)
    init_db()
    yield
    logger.info("Shutting down Personal Promo Offers API")


app = FastAPI(
    title="Personal Promo Offers API",
    description="Commercial-grade prototype: generates personalized promotional offers based on customer segment and price sensitivity.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception while processing %s %s", request.method, request.url)
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"detail": "Internal server error. Please contact support if this persists."})


@app.get("/health", response_model=HealthCheck, tags=["System"])
def health_check() -> HealthCheck:
    return HealthCheck(status="ok", environment=settings.app_env)


app.include_router(customers.router)
app.include_router(offers.router)
app.include_router(analytics.router)

app.mount("/app", StaticFiles(directory="frontend", html=True), name="frontend")
