from __future__ import annotations
import os
import time
from typing import Optional

_token_cache: dict[str, tuple] = {}   # token -> (result, expiry)
_player_cache: dict[str, tuple] = {}  # google_id -> (username, expiry)
_TOKEN_TTL = 300    # 5 min (Supabase tokens valid 1h, refreshed by SDK)
_PLAYER_TTL = 3600  # 1 hr (usernames don't change)

# Hidden domain used for native-signup accounts that skip providing a real email.
# Never sent to the browser — only ever compared against server-side.
PLACEHOLDER_EMAIL_DOMAIN = "users.pokedojo.internal"


def is_global_mode() -> bool:
    """Returns True when running against Supabase PostgreSQL (DATABASE_URL set)."""
    return bool(os.getenv("DATABASE_URL"))


def _cached_verify_token(access_token: str) -> Optional[dict]:
    now = time.time()
    if access_token in _token_cache:
        result, expiry = _token_cache[access_token]
        if now < expiry:
            return result
    result = verify_token(access_token)
    _token_cache[access_token] = (result, now + _TOKEN_TTL)
    return result


def _cached_player_username(google_id: str) -> Optional[str]:
    now = time.time()
    if google_id in _player_cache:
        username, expiry = _player_cache[google_id]
        if now < expiry:
            return username
    client = get_admin_client()
    row = client.table("players").select("username").eq("google_id", google_id).execute()
    username = row.data[0]["username"] if row.data else None
    _player_cache[google_id] = (username, now + _PLAYER_TTL)
    return username


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
    user = _cached_verify_token(access_token)
    if not user:
        return False
    cached_username = _cached_player_username(user["id"])
    return cached_username == username


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


def get_anon_client():
    """Anon-key client — used server-side for password sign-in (never sees the service key)."""
    from supabase import create_client
    return create_client(_url(), _anon_key())


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
