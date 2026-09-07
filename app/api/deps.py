"""Shared FastAPI dependencies for API routers."""

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.ab_test_service import ABTestService
from app.services.customer_service import CustomerService


def get_customer_service(db: Session = Depends(get_db)) -> CustomerService:
    return CustomerService(db)


def get_ab_test_service(db: Session = Depends(get_db)) -> ABTestService:
    return ABTestService(db)
