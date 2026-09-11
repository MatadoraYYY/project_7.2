"""Alternative entry point that adds the LLM endpoint to the existing app.

This file exists so that ``app/main.py`` requires no edits. It imports the
already-configured application object and attaches one extra router.

Run this entry point instead of the original one::

    uvicorn app.main_llm:app --reload

The original entry point keeps working unchanged::

    uvicorn app.main:app --reload
"""

from app.api import llm_offers
from app.core.logging_config import get_logger
from app.core.security import enforce_rate_limit
from app.main import app

from fastapi import Depends

logger = get_logger(__name__)

app.include_router(llm_offers.router, dependencies=[Depends(enforce_rate_limit)])
logger.info("LLM optimization endpoint registered at /api/v1/offers/optimization/recommendations/llm")
