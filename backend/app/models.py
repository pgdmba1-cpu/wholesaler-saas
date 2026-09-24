"""
SQLAlchemy table definitions — these describe the actual database
tables, as opposed to the Pydantic models in buyer_crm.py / auth.py,
which describe API input/output shapes. Keeping them separate is
normal: the DB layer and the API layer are allowed to look slightly
different.
"""

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.sql import func

from .database import Base


class UserModel(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    # Billing — set once someone subscribes via Stripe Checkout
    stripe_customer_id = Column(String, nullable=True)
    is_subscribed = Column(Boolean, nullable=False, default=False)


class SessionModel(Base):
    """
    An active login session. The 'token' is a random string handed to
    the browser after login; the browser sends it back on every
    request to prove who it is, instead of resending the password.
    """
    __tablename__ = "sessions"

    token = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class BuyerModel(Base):
    __tablename__ = "buyers"

    id = Column(String, primary_key=True)
    owner_id = Column(String, ForeignKey("users.id"), nullable=False)  # NEW — scopes data per user
    name = Column(String, nullable=False)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    buyer_type = Column(String, nullable=True)
    markets = Column(String, default="")           # stored as comma-separated text
    min_price = Column(Float, nullable=True)
    max_price = Column(Float, nullable=True)
    property_types = Column(String, default="")    # stored as comma-separated text
    min_beds = Column(Integer, nullable=True)
    notes = Column(String, nullable=True)


# Fixed pipeline stages, in order. Kept simple as a plain list rather
# than its own database table — good enough until stages need to be
# customized per user.
PIPELINE_STAGES = ["New Lead", "Under Contract", "Assigned", "Closed", "Dead"]


class DealModel(Base):
    __tablename__ = "deals"

    id = Column(String, primary_key=True)
    owner_id = Column(String, ForeignKey("users.id"), nullable=False)
    stage = Column(String, nullable=False, default="New Lead")

    address = Column(String, nullable=False)
    city = Column(String, nullable=True)
    contract_price = Column(Float, nullable=True)
    arv = Column(Float, nullable=True)
    notes = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
