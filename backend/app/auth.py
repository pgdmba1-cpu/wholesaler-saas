"""
Authentication.

Password hashing uses Python's built-in hashlib (PBKDF2) — deliberately
NOT a third-party library like bcrypt, because bcrypt needs a C compiler
to install, the exact problem that blocked psycopg2 earlier. PBKDF2 is
a legitimate, still-used password hashing algorithm and needs nothing
extra installed.

Sessions are "opaque tokens": after login, the server hands back a
random string and remembers it in the sessions table. The browser
sends that string back on every request (as an Authorization header)
to prove who it is, instead of resending the password each time.
"""

from __future__ import annotations

import binascii
import hashlib
import os
import secrets
import uuid
from typing import Optional

from fastapi import Depends, Header, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from .database import get_db
from .models import SessionModel, UserModel

PBKDF2_ITERATIONS = 100_000


# ---------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"{binascii.hexlify(salt).decode()}:{binascii.hexlify(derived).decode()}"


def verify_password(password: str, stored_hash: str) -> bool:
    salt_hex, hash_hex = stored_hash.split(":")
    salt = binascii.unhexlify(salt_hex)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return secrets.compare_digest(binascii.hexlify(derived).decode(), hash_hex)


# ---------------------------------------------------------------
# API models
# ---------------------------------------------------------------

class SignupIn(BaseModel):
    email: EmailStr
    password: str


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class User(BaseModel):
    id: str
    email: str
    is_subscribed: bool = False


class TokenOut(BaseModel):
    access_token: str
    user: User


# ---------------------------------------------------------------
# Signup / login
# ---------------------------------------------------------------

def signup(db: Session, payload: SignupIn) -> TokenOut:
    existing = db.query(UserModel).filter(UserModel.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="An account with that email already exists.")

    user = UserModel(
        id=str(uuid.uuid4()),
        email=payload.email,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return _create_session(db, user)


def login(db: Session, payload: LoginIn) -> TokenOut:
    user = db.query(UserModel).filter(UserModel.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")

    return _create_session(db, user)


def _create_session(db: Session, user: UserModel) -> TokenOut:
    token = secrets.token_hex(32)
    db.add(SessionModel(token=token, user_id=user.id))
    db.commit()
    return TokenOut(
        access_token=token,
        user=User(id=user.id, email=user.email, is_subscribed=user.is_subscribed),
    )


# ---------------------------------------------------------------
# Dependency: figure out who's making the request
# ---------------------------------------------------------------

def get_current_user(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    """
    Reads the 'Authorization: Bearer <token>' header, looks up the
    session, and returns the logged-in user — or rejects the request
    with 401 if the token is missing or invalid.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not logged in.")

    token = authorization.removeprefix("Bearer ").strip()
    session = db.query(SessionModel).filter(SessionModel.token == token).first()
    if not session:
        raise HTTPException(status_code=401, detail="Session expired or invalid — please log in again.")

    user = db.query(UserModel).filter(UserModel.id == session.user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User no longer exists.")

    return User(id=user.id, email=user.email, is_subscribed=user.is_subscribed)
