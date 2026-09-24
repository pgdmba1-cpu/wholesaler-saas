"""
Buyer CRM — store buyers and match them against a deal.

Storage is now a real SQLite database (see database.py, models.py).
The matching logic (score_buyer) is unchanged from before — it still
works on plain Pydantic Buyer objects, so the "brains" of the CRM
didn't need to change at all when storage moved from memory to disk.
"""

from __future__ import annotations

import uuid
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .models import BuyerModel


# ---------------------------------------------------------------
# API-facing models (unchanged from the in-memory version)
# ---------------------------------------------------------------

class BuyerIn(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    buyer_type: Optional[str] = None
    markets: list[str] = Field(default_factory=list)
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    property_types: list[str] = Field(default_factory=list)
    min_beds: Optional[int] = None
    notes: Optional[str] = None


class Buyer(BuyerIn):
    id: str


class DealMatchInput(BaseModel):
    market: str
    price: float
    property_type: Optional[str] = None
    beds: Optional[int] = None


class BuyerMatch(BaseModel):
    buyer: Buyer
    score: float
    reasons: list[str]


# ---------------------------------------------------------------
# Conversion helpers: DB row <-> API model
# ---------------------------------------------------------------

def _to_pydantic(row: BuyerModel) -> Buyer:
    return Buyer(
        id=row.id,
        name=row.name,
        email=row.email,
        phone=row.phone,
        buyer_type=row.buyer_type,
        markets=[m for m in (row.markets or "").split(",") if m],
        min_price=row.min_price,
        max_price=row.max_price,
        property_types=[p for p in (row.property_types or "").split(",") if p],
        min_beds=row.min_beds,
        notes=row.notes,
    )


# ---------------------------------------------------------------
# Storage (now backed by SQLite)
# ---------------------------------------------------------------

def add_buyer(db: Session, payload: BuyerIn, owner_id: str) -> Buyer:
    row = BuyerModel(
        id=str(uuid.uuid4()),
        owner_id=owner_id,
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        buyer_type=payload.buyer_type,
        markets=",".join(payload.markets),
        min_price=payload.min_price,
        max_price=payload.max_price,
        property_types=",".join(payload.property_types),
        min_beds=payload.min_beds,
        notes=payload.notes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_pydantic(row)


def list_buyers(db: Session, owner_id: str) -> list[Buyer]:
    rows = db.query(BuyerModel).filter(BuyerModel.owner_id == owner_id).all()
    return [_to_pydantic(row) for row in rows]


# ---------------------------------------------------------------
# Matching logic — identical to before, still framework-agnostic
# ---------------------------------------------------------------

def score_buyer(buyer: Buyer, deal: DealMatchInput) -> BuyerMatch:
    score = 0.0
    reasons: list[str] = []

    price_ok = True
    if buyer.min_price is not None and deal.price < buyer.min_price:
        price_ok = False
        reasons.append(f"Deal price (${deal.price:,.0f}) is below buyer's min (${buyer.min_price:,.0f})")
    if buyer.max_price is not None and deal.price > buyer.max_price:
        price_ok = False
        reasons.append(f"Deal price (${deal.price:,.0f}) is above buyer's max (${buyer.max_price:,.0f})")
    if price_ok:
        score += 40
        reasons.append("Price is within buyer's range")

    if not buyer.markets:
        score += 15
        reasons.append("Buyer has no market restriction on file")
    elif deal.market in buyer.markets:
        score += 30
        reasons.append(f"Buyer is active in {deal.market}")
    else:
        reasons.append(f"Buyer does not list {deal.market} as a target market")

    if not buyer.property_types or deal.property_type is None:
        score += 10
        reasons.append("Property type not restricted or not specified")
    elif deal.property_type in buyer.property_types:
        score += 20
        reasons.append(f"Buyer buys {deal.property_type}")
    else:
        reasons.append(f"Buyer doesn't typically buy {deal.property_type}")

    if buyer.min_beds is None or deal.beds is None:
        score += 5
        reasons.append("Bed count not restricted or not specified")
    elif deal.beds >= buyer.min_beds:
        score += 10
        reasons.append(f"Meets buyer's minimum of {buyer.min_beds} beds")
    else:
        reasons.append(f"Below buyer's minimum of {buyer.min_beds} beds")

    return BuyerMatch(buyer=buyer, score=round(score, 1), reasons=reasons)


def match_deal(db: Session, deal: DealMatchInput, owner_id: str, min_score: float = 0.0) -> list[BuyerMatch]:
    matches = [score_buyer(b, deal) for b in list_buyers(db, owner_id)]
    matches = [m for m in matches if m.score >= min_score]
    return sorted(matches, key=lambda m: m.score, reverse=True)
