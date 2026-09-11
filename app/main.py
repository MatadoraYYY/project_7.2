"""FastAPI application entry point."""

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api import analytics, customers, offers
from app.core.config import get_settings
from app.core.database import init_db
from app.core.logging_config import configure_logging, get_logger
from app.core.security import enforce_rate_limit
from app.models.schemas import HealthCheck

configure_logging()
logger = get_logger(__name__)
settings = get_settings()

app = FastAPI(
    title="Personal Promo Offers API",
    description=(
        "Система персональных промо-предложений: ценовая эластичность, сегментация, "
        "генерация и оптимизация офферов, кампании и A/B-тестирование."
    ),
    version="1.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(customers.router, dependencies=[Depends(enforce_rate_limit)])
app.include_router(offers.router, dependencies=[Depends(enforce_rate_limit)])
app.include_router(analytics.router, dependencies=[Depends(enforce_rate_limit)])

app.mount("/app", StaticFiles(directory="frontend", html=True), name="dashboard")


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    logger.info("Starting Personal Promo Offers API in '%s' environment", settings.app_env)


@app.get("/", include_in_schema=False)
def root_redirect() -> RedirectResponse:
    return RedirectResponse(url="/app/")


@app.get("/health", response_model=HealthCheck, tags=["System"])
def health_check() -> HealthCheck:
    """Liveness probe."""
    return HealthCheck(status="ok", environment=settings.app_env)
