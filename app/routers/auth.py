from __future__ import annotations
import re
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import supabase_client
from app.services.username_filter import is_banned

router = APIRouter(prefix="/auth", tags=["auth"])

_USERNAME_MIN = 3
_USERNAME_MAX = 20


class ClaimRequest(BaseModel):
    access_token: str
    username: str


class ClaimResponse(BaseModel):
    ok: bool
    username: str


class VerifyRequest(BaseModel):
    access_token: str


class VerifyResponse(BaseModel):
    authenticated: bool
    username: str | None = None


@router.post("/claim-username", response_model=ClaimResponse)
def claim_username(req: ClaimRequest):
    if not supabase_client.is_configured():
        raise HTTPException(503, "Global features not configured on this instance")

    name = req.username.strip().lower()
    if len(name) < _USERNAME_MIN or len(name) > _USERNAME_MAX:
        raise HTTPException(400, f"Username must be {_USERNAME_MIN}–{_USERNAME_MAX} characters")
    if not all(c.isalnum() or c in "-_" for c in name):
        raise HTTPException(400, "Only letters, numbers, hyphens, and underscores allowed")
    if name.isdigit():
        raise HTTPException(400, "Username must contain at least one letter")
    if re.search(r'\d{7,}', name):
        raise HTTPException(400, "Avoid phone numbers or long digit sequences in your username")
    if is_banned(name):
        raise HTTPException(400, "That name is not allowed")

    user = supabase_client.verify_token(req.access_token)
    if not user:
        raise HTTPException(401, "Invalid or expired session")

    client = supabase_client.get_admin_client()

    # If this Google account already has a username, return it (idempotent)
    existing = client.table("players").select("username").eq("google_id", user["id"]).execute()
    if existing.data:
        return ClaimResponse(ok=True, username=existing.data[0]["username"])

    # Check availability
    taken = client.table("players").select("id").eq("username", name).execute()
    if taken.data:
        raise HTTPException(409, "Username already taken — choose another")

    client.table("players").insert({"google_id": user["id"], "username": name}).execute()
    return ClaimResponse(ok=True, username=name)


@router.post("/verify", response_model=VerifyResponse)
def verify(req: VerifyRequest):
    """Verify a JWT and return the claimed username if any. Safe to call on every page load."""
    if not supabase_client.is_configured():
        return VerifyResponse(authenticated=False)

    user = supabase_client.verify_token(req.access_token)
    if not user:
        return VerifyResponse(authenticated=False)

    client = supabase_client.get_admin_client()
    row = client.table("players").select("username").eq("google_id", user["id"]).execute()
    username = row.data[0]["username"] if row.data else None
    return VerifyResponse(authenticated=True, username=username)
