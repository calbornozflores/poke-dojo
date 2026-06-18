from __future__ import annotations
import os
from typing import Optional


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
