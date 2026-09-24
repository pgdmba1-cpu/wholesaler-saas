"""
FastAPI entrypoint.

Run locally:
    pip install -r requirements.txt
    uvicorn app.main:app --reload

Buyers now belong to a specific logged-in user — sign up, log in, and
send the returned access_token as an "Authorization: Bearer <token>"
header on /buyers requests.
"""

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .auth import LoginIn, SignupIn, TokenOut, User, get_current_user, login, signup
from .billing import create_checkout_session, handle_webhook
from .buyer_crm import Buyer, BuyerIn, BuyerMatch, DealMatchInput, add_buyer, list_buyers, match_deal
from .database import Base, engine, get_db
from .deal_analyzer import DealAnalysis, DealInput, analyze_deal
from .deal_pipeline import Deal, DealIn, StageUpdate, create_deal, list_deals, update_stage
from .models import PIPELINE_STAGES

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Wholesaler SaaS API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # wide open for local development — tighten before going live
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------------- Auth ----------------

@app.post("/auth/signup", response_model=TokenOut)
def auth_signup(payload: SignupIn, db: Session = Depends(get_db)):
    return signup(db, payload)


@app.post("/auth/login", response_model=TokenOut)
def auth_login(payload: LoginIn, db: Session = Depends(get_db)):
    return login(db, payload)


@app.get("/auth/me", response_model=User)
def auth_me(current_user: User = Depends(get_current_user)):
    return current_user


# ---------------- Deal Analyzer (not user-specific, doesn't need login) ----------------

@app.post("/deals/analyze", response_model=DealAnalysis)
def analyze(payload: DealInput):
    try:
        return analyze_deal(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------- Buyer CRM (requires login, scoped to the logged-in user) ----------------

@app.post("/buyers", response_model=Buyer)
def create_buyer(
    payload: BuyerIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return add_buyer(db, payload, owner_id=current_user.id)


@app.get("/buyers", response_model=list[Buyer])
def get_buyers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return list_buyers(db, owner_id=current_user.id)


@app.post("/buyers/match", response_model=list[BuyerMatch])
def match_buyers(
    payload: DealMatchInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return match_deal(db, payload, owner_id=current_user.id)


# ---------------- Deal Pipeline (requires login, scoped to the logged-in user) ----------------

@app.get("/pipeline/stages", response_model=list[str])
def get_pipeline_stages():
    return PIPELINE_STAGES


@app.post("/deals", response_model=Deal)
def create_deal_endpoint(
    payload: DealIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return create_deal(db, payload, owner_id=current_user.id)


@app.get("/deals", response_model=list[Deal])
def get_deals(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return list_deals(db, owner_id=current_user.id)


@app.patch("/deals/{deal_id}/stage", response_model=Deal)
def update_deal_stage(
    deal_id: str,
    payload: StageUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return update_stage(db, deal_id, owner_id=current_user.id, new_stage=payload.stage)


# ---------------- Billing ----------------

@app.post("/billing/checkout")
def billing_checkout(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    url = create_checkout_session(db, current_user)
    return {"url": url}


@app.post("/billing/webhook")
async def billing_webhook(request: Request, db: Session = Depends(get_db)):
    return await handle_webhook(request, db)
