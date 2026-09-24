"""
Deal Analyzer — core calculation engine.

Covers the three things a wholesaler needs from a deal:
  1. ARV (after-repair value) estimated from comparable sales
  2. MAO (max allowable offer) using the configurable "X% rule"
  3. Deal economics — assignment fee, margin, and a go/no-go flag

Framework-agnostic on purpose: import `analyze_deal()` from a FastAPI
route, a Celery task, or a unit test with no changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------
# Input models
# ---------------------------------------------------------------

class Comp(BaseModel):
    """A single comparable sale used to derive ARV."""
    address: str
    sale_price: float = Field(gt=0)
    sqft: Optional[int] = Field(default=None, gt=0)
    distance_miles: Optional[float] = Field(default=None, ge=0)
    sale_date: Optional[str] = None  # ISO date string, kept loose for API input

    @property
    def price_per_sqft(self) -> Optional[float]:
        if self.sqft:
            return round(self.sale_price / self.sqft, 2)
        return None


class DealInput(BaseModel):
    subject_sqft: int = Field(gt=0, description="Square footage of the subject property")
    repair_estimate: float = Field(ge=0, default=0)
    contract_price: float = Field(gt=0, description="Price under contract with the seller")

    comps: list[Comp] = Field(default_factory=list, description="Comparable sales")
    manual_arv: Optional[float] = Field(
        default=None, description="Override ARV directly instead of deriving it from comps"
    )

    # Rule configuration — defaults follow the common wholesaling "70% rule"
    investor_margin_pct: float = Field(
        default=0.30, ge=0, le=1,
        description="Target margin the end buyer needs, e.g. 0.30 for the 70% rule",
    )
    target_assignment_fee: float = Field(
        default=10000, ge=0,
        description="Wholesaler's desired fee, subtracted from MAO headroom",
    )

    @field_validator("comps")
    @classmethod
    def _require_comps_or_manual_arv(cls, v, info):
        return v  # validated jointly in analyze_deal(); kept permissive here


# ---------------------------------------------------------------
# Output models
# ---------------------------------------------------------------

class DealAnalysis(BaseModel):
    arv: float
    arv_method: str                  # "comps" | "manual"
    comp_count: int
    avg_price_per_sqft: Optional[float]

    mao: float                       # max allowable offer to the seller
    contract_price: float
    repair_estimate: float

    max_assignment_fee: float        # headroom between MAO and contract price
    projected_assignment_fee: float  # clamped to what the deal can actually support
    end_buyer_all_in_cost: float     # contract_price + repairs + assignment fee, from buyer's view
    end_buyer_margin_pct: float      # actual margin the end buyer gets at this price

    is_viable: bool                  # True if contract_price <= MAO
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------
# Core calculation
# ---------------------------------------------------------------

def estimate_arv(comps: list[Comp], subject_sqft: int) -> tuple[float, Optional[float]]:
    """
    Estimate ARV as (average $/sqft across comps) * subject sqft.
    Falls back to a straight average of comp sale prices if sqft data
    is missing on comps.
    """
    per_sqft_values = [c.price_per_sqft for c in comps if c.price_per_sqft]

    if per_sqft_values:
        avg_psf = round(mean(per_sqft_values), 2)
        return round(avg_psf * subject_sqft, 2), avg_psf

    # fallback: no usable sqft data on any comp
    prices = [c.sale_price for c in comps]
    return round(mean(prices), 2), None


def analyze_deal(payload: DealInput) -> DealAnalysis:
    notes: list[str] = []

    # --- ARV ---
    if payload.manual_arv is not None:
        arv = payload.manual_arv
        arv_method = "manual"
        avg_psf = None
    else:
        if not payload.comps:
            raise ValueError("Provide at least one comp or a manual_arv override.")
        arv, avg_psf = estimate_arv(payload.comps, payload.subject_sqft)
        arv_method = "comps"
        if len(payload.comps) < 3:
            notes.append("Fewer than 3 comps used — ARV confidence is low.")

    # --- MAO (the "X% rule") ---
    # MAO = ARV * (1 - investor_margin_pct) - repair_estimate
    mao = round(arv * (1 - payload.investor_margin_pct) - payload.repair_estimate, 2)

    # --- Assignment economics ---
    max_assignment_fee = round(mao - payload.contract_price, 2)
    projected_assignment_fee = max(0.0, min(payload.target_assignment_fee, max_assignment_fee))

    end_buyer_all_in_cost = round(
        payload.contract_price + payload.repair_estimate + projected_assignment_fee, 2
    )
    end_buyer_margin_pct = (
        round((arv - end_buyer_all_in_cost) / arv, 4) if arv else 0.0
    )

    is_viable = payload.contract_price <= mao

    if not is_viable:
        notes.append(
            f"Contract price (${payload.contract_price:,.0f}) exceeds MAO "
            f"(${mao:,.0f}) — no room for an assignment fee at the target margin."
        )
    elif projected_assignment_fee < payload.target_assignment_fee:
        notes.append(
            f"Deal only supports a ${projected_assignment_fee:,.0f} fee, "
            f"below your ${payload.target_assignment_fee:,.0f} target."
        )

    return DealAnalysis(
        arv=arv,
        arv_method=arv_method,
        comp_count=len(payload.comps),
        avg_price_per_sqft=avg_psf,
        mao=mao,
        contract_price=payload.contract_price,
        repair_estimate=payload.repair_estimate,
        max_assignment_fee=max_assignment_fee,
        projected_assignment_fee=projected_assignment_fee,
        end_buyer_all_in_cost=end_buyer_all_in_cost,
        end_buyer_margin_pct=end_buyer_margin_pct,
        is_viable=is_viable,
        notes=notes,
    )
