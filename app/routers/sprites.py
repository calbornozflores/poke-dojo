from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from app.services.sprite_proxy import (
    MAX_POKEMON_ID,
    MIN_POKEMON_ID,
    TYPE_IDS,
    cache_path,
    fetch_and_cache,
    upstream_url_for,
    upstream_url_for_type,
)

router = APIRouter(prefix="/sprites", tags=["sprites"])

_CACHE_HEADERS = {"Cache-Control": "public, max-age=31536000, immutable"}


def _validate_pokemon_id(pokemon_id: int) -> None:
    if not (MIN_POKEMON_ID <= pokemon_id <= MAX_POKEMON_ID):
        raise HTTPException(status_code=404, detail="unknown pokemon id")


async def _serve(kind: str, key: str, upstream_url: str) -> Response:
    dest = cache_path(kind, key)
    if dest.exists():
        return FileResponse(dest, media_type="image/png", headers=_CACHE_HEADERS)

    content = await fetch_and_cache(upstream_url, dest)
    if content is None:
        raise HTTPException(status_code=502, detail="sprite unavailable")
    return Response(content=content, media_type="image/png", headers=_CACHE_HEADERS)


@router.get("/pokemon/{pokemon_id}.png")
async def get_pokemon_sprite(pokemon_id: int) -> Response:
    _validate_pokemon_id(pokemon_id)
    return await _serve("pokemon", str(pokemon_id), upstream_url_for("pokemon", pokemon_id))


@router.get("/artwork/{pokemon_id}.png")
async def get_pokemon_artwork(pokemon_id: int) -> Response:
    _validate_pokemon_id(pokemon_id)
    return await _serve("artwork", str(pokemon_id), upstream_url_for("artwork", pokemon_id))


@router.get("/type/{type_name}.png")
async def get_type_icon(type_name: str) -> Response:
    icon_id = TYPE_IDS.get(type_name)
    if icon_id is None:
        raise HTTPException(status_code=404, detail="unknown type")
    return await _serve("type", type_name, upstream_url_for_type(icon_id))
