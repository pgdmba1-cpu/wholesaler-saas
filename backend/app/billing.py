"""
Billing via Stripe Checkout.

Flow:
1. Logged-in user clicks "Upgrade" -> POST /billing/checkout -> we create a
   Stripe Checkout Session and return its URL.
2. Browser redirects the user to that URL (Stripe's own hosted payment
   page — we never see or touch card numbers, which is exactly the
   point: Stripe handles that securely so we don't have to).
3. After payment, Stripe redirects the user back to our site AND
   separately calls our webhook endpoint (POST /billing/webhook) to
   tell us, server-to-server, that payment succeeded. We only mark
   the user as subscribed once the webhook confirms it — never from
   the redirect alone, since a redirect can be faked but a verified
   webhook signature can't.

Configuration comes from environment variables (never hardcoded, never
committed to Git):
  STRIPE_SECRET_KEY   - starts with sk_test_... (or sk_live_ in production)
  STRIPE_PRICE_ID     - starts with price_...
  STRIPE_WEBHOOK_SECRET - starts with whsec_...
  FRONTEND_URL        - your Netlify URL, so Stripe knows where to send
                         the user back after checkout
"""

from __future__ import annotations

import os

import stripe
from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from .models import UserModel

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")

STRIPE_PRICE_ID = os.environ.get("STRIPE_PRICE_ID", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost")


def create_checkout_session(db: Session, user: UserModel) -> str:
    if not stripe.api_key or not STRIPE_PRICE_ID:
        raise HTTPException(status_code=500, detail="Billing isn't configured yet.")

    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
        customer_email=user.email,
        client_reference_id=user.id,  # lets the webhook match payment back to this user
        success_url=f"{FRONTEND_URL}?billing=success",
        cancel_url=f"{FRONTEND_URL}?billing=cancelled",
    )
    return session.url


async def handle_webhook(request: Request, db: Session) -> dict:
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(status_code=400, detail="Invalid webhook signature.")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = session.get("client_reference_id")
        customer_id = session.get("customer")

        user = db.query(UserModel).filter(UserModel.id == user_id).first()
        if user:
            user.is_subscribed = True
            user.stripe_customer_id = customer_id
            db.commit()

    return {"received": True}
