from __future__ import annotations
import os
from typing import Optional


def is_global_mode() -> bool:
    """Returns True when running against Supabase PostgreSQL (DATABASE_URL set)."""
    return bool(os.getenv("DATABASE_URL"))


def is_authenticated_user(username: str, access_token: Optional[str]) -> bool:
    """
    In global PostgreSQL mode: verify the Supabase token and confirm the username
    matches the players table. Only these users get their data persisted globally.
    In local SQLite mode: always returns True (all users saved locally).
    """
    if not is_global_mode():
        return True
    if not access_token:
        return False
    if not is_configured():
        return False
    user = verify_token(access_token)
    if not user:
        return False
    client = get_admin_client()
    row = client.table("players").select("username").eq("google_id", user["id"]).execute()
    return bool(row.data) and row.data[0]["username"] == username


def _url() -> str:
    return os.getenv("SUPABASE_URL", "")


def _anon_key() -> str:
    return os.getenv("SUPABASE_ANON_KEY", "")


def _service_key() -> str:
    return os.getenv("SUPABASE_SERVICE_KEY", "")


def is_configured() -> bool:
    return bool(_url() and _anon_key() and _service_key())


def get_admin_client():
    """Service-role client — bypasses RLS. Used only server-side, never sent to browser."""
    from supabase import create_client
    return create_client(_url(), _service_key())


def verify_token(access_token: str) -> Optional[dict]:
    """Verify a Supabase JWT. Returns {id, email} on success, None if invalid."""
    try:
        from supabase import create_client
        client = create_client(_url(), _anon_key())
        resp = client.auth.get_user(access_token)
        if resp.user:
            return {"id": str(resp.user.id), "email": resp.user.email}
    except Exception:
        pass
    return None
