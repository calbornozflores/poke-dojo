from __future__ import annotations
import os
import re
import secrets
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from sqlalchemy.orm import Session
from fastapi import Depends

from app.database import get_db
from app.models import User
from app.services import supabase_client
from app.services.username_filter import validate_username
from app.services.level_system import level_from_xp, xp_progress_in_current_level
from app.routers.scores import get_user_rank

_EMAIL_RE = re.compile(r'[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}', re.IGNORECASE)
_PASSWORD_MIN = 8

MAX_PLAYERS = int(os.getenv("MAX_PLAYERS", "500"))

router = APIRouter(prefix="/auth", tags=["auth"])


def _insert_player(client, uid: str, name: str) -> None:
    """Enforce the player cap + username uniqueness, then insert. Shared by
    claim_username (Google) and signup (native)."""
    total = client.table("players").select("id", count="exact").execute()
    if (total.count or 0) >= MAX_PLAYERS:
        raise HTTPException(429, "The Dojo is at capacity — check back later")

    taken = client.table("players").select("id").eq("username", name).execute()
    if taken.data:
        raise HTTPException(409, "Username already taken — choose another")

    client.table("players").insert({"google_id": uid, "username": name}).execute()


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


class SignupRequest(BaseModel):
    username: str
    password: str
    email: str | None = None


class SignupResponse(BaseModel):
    ok: bool
    username: str
    access_token: str | None = None
    refresh_token: str | None = None
    email_confirmation_pending: bool = False


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    ok: bool
    access_token: str | None = None
    refresh_token: str | None = None
    username: str | None = None


@router.post("/claim-username", response_model=ClaimResponse)
def claim_username(req: ClaimRequest):
    if not supabase_client.is_configured():
        raise HTTPException(503, "Global features not configured on this instance")

    name = req.username.strip().lower()
    err = validate_username(name)
    if err:
        raise HTTPException(400, err)

    user = supabase_client.verify_token(req.access_token)
    if not user:
        raise HTTPException(401, "Invalid or expired session")

    client = supabase_client.get_admin_client()

    # If this account already has a username, return it (idempotent)
    existing = client.table("players").select("username").eq("google_id", user["id"]).execute()
    if existing.data:
        return ClaimResponse(ok=True, username=existing.data[0]["username"])

    _insert_player(client, user["id"], name)
    return ClaimResponse(ok=True, username=name)


@router.post("/signup", response_model=SignupResponse)
def signup(req: SignupRequest):
    """Native username+password signup. Uses Supabase Auth's own password
    storage via the Admin API — no custom password handling here.

    If no email is given, a hidden placeholder email is generated so
    Supabase still has a real, working account; that account is
    force-confirmed since there's no inbox to click a confirmation link in.
    A real email goes through Supabase's normal confirmation flow instead.
    """
    if not supabase_client.is_configured():
        raise HTTPException(503, "Global features not configured on this instance")

    name = req.username.strip().lower()
    err = validate_username(name)
    if err:
        raise HTTPException(400, err)

    if len(req.password) < _PASSWORD_MIN:
        raise HTTPException(400, f"Password must be at least {_PASSWORD_MIN} characters")

    real_email = req.email.strip().lower() if req.email else None
    if real_email and not _EMAIL_RE.fullmatch(real_email):
        raise HTTPException(400, "That doesn't look like a valid email address")

    is_placeholder = real_email is None
    final_email = real_email or f"{secrets.token_hex(10)}@{supabase_client.PLACEHOLDER_EMAIL_DOMAIN}"

    admin = supabase_client.get_admin_client()
    try:
        created = admin.auth.admin.create_user({
            "email": final_email,
            "password": req.password,
            "email_confirm": is_placeholder,
        })
    except Exception:
        raise HTTPException(400, "Could not create account — try a different email")

    uid = str(created.user.id)

    try:
        _insert_player(admin, uid, name)
    except HTTPException:
        admin.auth.admin.delete_user(uid)
        raise

    anon = supabase_client.get_anon_client()
    try:
        signin = anon.auth.sign_in_with_password({"email": final_email, "password": req.password})
        return SignupResponse(
            ok=True, username=name,
            access_token=signin.session.access_token,
            refresh_token=signin.session.refresh_token,
        )
    except Exception:
        # Real email pending confirmation — account + username exist, no session yet
        return SignupResponse(ok=True, username=name, email_confirmation_pending=not is_placeholder)


@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest):
    """Native username+password login. Resolves username -> email entirely
    server-side so no email (real or placeholder) ever reaches the browser."""
    if not supabase_client.is_configured():
        raise HTTPException(503, "Global features not configured on this instance")

    name = req.username.strip().lower()
    admin = supabase_client.get_admin_client()
    row = admin.table("players").select("google_id").eq("username", name).execute()

    generic_error = HTTPException(401, "Invalid username or password")
    if not row.data:
        raise generic_error

    uid = row.data[0]["google_id"]
    try:
        user = admin.auth.admin.get_user_by_id(uid)
        email = user.user.email
        anon = supabase_client.get_anon_client()
        signin = anon.auth.sign_in_with_password({"email": email, "password": req.password})
    except Exception:
        raise generic_error

    return LoginResponse(
        ok=True, username=name,
        access_token=signin.session.access_token,
        refresh_token=signin.session.refresh_token,
    )


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


class ProfileRequest(BaseModel):
    access_token: str


class ProfileResponse(BaseModel):
    username: str
    player_level: int
    total_xp: float
    xp_current: float
    xp_needed: float
    rank: int | None
    ranked_total: int
    email: str
    is_native: bool
    has_real_email: bool


@router.post("/profile", response_model=ProfileResponse)
def profile(req: ProfileRequest, db: Session = Depends(get_db)):
    """Private account info for the signed-in player. The uid comes exclusively
    from the verified JWT, never from the request body — no way to fetch
    another user's data."""
    if not supabase_client.is_configured():
        raise HTTPException(503, "Global features not configured on this instance")

    user = supabase_client.verify_token(req.access_token)
    if not user:
        raise HTTPException(401, "Invalid or expired session")

    admin = supabase_client.get_admin_client()
    row = admin.table("players").select("username").eq("google_id", user["id"]).execute()
    if not row.data:
        raise HTTPException(404, "No account found — claim a username first")
    username = row.data[0]["username"]

    local_user = db.query(User).filter(User.username == username).first()
    total_xp = local_user.total_xp if local_user else 0.0
    player_level = level_from_xp(total_xp)
    xp_current, xp_needed = xp_progress_in_current_level(total_xp)
    rank, ranked_total = get_user_rank(db, username, total_xp)

    auth_user = admin.auth.admin.get_user_by_id(user["id"]).user
    providers = auth_user.app_metadata.get("providers") or [auth_user.app_metadata.get("provider")]
    is_native = "google" not in providers
    email = auth_user.email or ""
    has_real_email = bool(email) and not email.endswith(f"@{supabase_client.PLACEHOLDER_EMAIL_DOMAIN}")

    return ProfileResponse(
        username=username,
        player_level=player_level,
        total_xp=round(total_xp, 1),
        xp_current=xp_current,
        xp_needed=xp_needed,
        rank=rank,
        ranked_total=ranked_total,
        email=email,
        is_native=is_native,
        has_real_email=has_real_email,
    )
