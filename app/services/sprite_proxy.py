"""Same-origin proxy/cache for Pokémon sprite images.

Sprites are hosted on raw.githubusercontent.com, which some mobile
networks/carriers and mobile ad/privacy blockers block even when the
device otherwise has normal internet access. Serving sprites from this
app's own origin (with a disk cache) removes that dependency.
"""
import re
from pathlib import Path

import httpx

CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "sprite_cache"

_GITHUB_BASE = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites"

_UPSTREAM_URLS = {
    "pokemon": _GITHUB_BASE + "/pokemon/{id}.png",
    "artwork": _GITHUB_BASE + "/pokemon/other/official-artwork/{id}.png",
}

TYPE_IDS = {
    "normal": 1, "fighting": 2, "flying": 3, "poison": 4, "ground": 5,
    "rock": 6, "bug": 7, "ghost": 8, "steel": 9, "fire": 10, "water": 11,
    "grass": 12, "electric": 13, "psychic": 14, "ice": 15, "dragon": 16,
    "dark": 17, "fairy": 18,
}

_TYPE_UPSTREAM = _GITHUB_BASE + "/types/generation-ix/scarlet-violet/{icon_id}.png"

MIN_POKEMON_ID = 1
MAX_POKEMON_ID = 2000

_REWRITE_PATTERNS = [
    (re.compile(r"raw\.githubusercontent\.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/(\d+)\.png"), "artwork"),
    (re.compile(r"raw\.githubusercontent\.com/PokeAPI/sprites/master/sprites/pokemon/(\d+)\.png"), "pokemon"),
]


def proxy_url(pokemon_id: int, kind: str = "pokemon") -> str:
    """Build the local same-origin proxy path for a Pokémon sprite."""
    if kind not in _UPSTREAM_URLS:
        raise ValueError(f"unknown sprite kind: {kind!r}")
    return f"/sprites/{kind}/{pokemon_id}.png"


def type_proxy_url(type_name: str) -> str:
    return f"/sprites/type/{type_name}.png"


def rewrite_sprite_url(raw_url: str) -> str:
    """Map a stored raw.githubusercontent.com sprite URL to the local proxy path.

    Returns the URL unchanged if it doesn't match a known pattern (e.g.
    it's already a local path, or some other CDN URL).
    """
    if not raw_url:
        return raw_url
    for pattern, kind in _REWRITE_PATTERNS:
        match = pattern.search(raw_url)
        if match:
            return proxy_url(int(match.group(1)), kind)
    return raw_url


def upstream_url_for(kind: str, pokemon_id: int) -> str:
    return _UPSTREAM_URLS[kind].format(id=pokemon_id)


def upstream_url_for_type(icon_id: int) -> str:
    return _TYPE_UPSTREAM.format(icon_id=icon_id)


def cache_path(kind: str, key: str) -> Path:
    return CACHE_DIR / kind / f"{key}.png"


async def fetch_and_cache(upstream_url: str, dest: Path) -> bytes | None:
    """Fetch an image from upstream and atomically write it to the disk cache.

    Returns the image bytes on success, None on any failure (timeout,
    non-200, network error) so callers can respond with a clean error
    instead of raising.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
            resp = await client.get(upstream_url)
            resp.raise_for_status()
            content = resp.content
    except httpx.HTTPError:
        return None

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    tmp.write_bytes(content)
    tmp.replace(dest)
    return content
