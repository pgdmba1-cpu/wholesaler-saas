"""
Deal Pipeline — save deals and track them through pipeline stages
(New Lead -> Under Contract -> Assigned -> Closed, or Dead).

Follows the same pattern as buyer_crm.py: Pydantic models for the API
shape, a SQLAlchemy model for storage, and plain functions in between
that main.py calls from each endpoint.
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .models import PIPELINE_STAGES, DealModel


# ---------------------------------------------------------------
# API models
# ---------------------------------------------------------------

class DealIn(BaseModel):
    address: str
    city: Optional[str] = None
    contract_price: Optional[float] = None
    arv: Optional[float] = None
    notes: Optional[str] = None


class Deal(DealIn):
    id: str
    stage: str


class StageUpdate(BaseModel):
    stage: str


# ---------------------------------------------------------------
# Conversion helper
# ---------------------------------------------------------------

def _to_pydantic(row: DealModel) -> Deal:
    return Deal(
        id=row.id,
        stage=row.stage,
        address=row.address,
        city=row.city,
        contract_price=row.contract_price,
        arv=row.arv,
        notes=row.notes,
    )


# ---------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------

def create_deal(db: Session, payload: DealIn, owner_id: str) -> Deal:
    row = DealModel(
        id=str(uuid.uuid4()),
        owner_id=owner_id,
        stage=PIPELINE_STAGES[0],  # every new deal starts at "New Lead"
        address=payload.address,
        city=payload.city,
        contract_price=payload.contract_price,
        arv=payload.arv,
        notes=payload.notes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_pydantic(row)


def list_deals(db: Session, owner_id: str) -> list[Deal]:
    rows = db.query(DealModel).filter(DealModel.owner_id == owner_id).all()
    return [_to_pydantic(row) for row in rows]


def update_stage(db: Session, deal_id: str, owner_id: str, new_stage: str) -> Deal:
    if new_stage not in PIPELINE_STAGES:
        raise HTTPException(
            status_code=400,
            detail=f"'{new_stage}' isn't a valid stage. Choose from: {', '.join(PIPELINE_STAGES)}",
        )

    row = (
        db.query(DealModel)
        .filter(DealModel.id == deal_id, DealModel.owner_id == owner_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Deal not found.")

    row.stage = new_stage
    db.commit()
    db.refresh(row)
    return _to_pydantic(row)
