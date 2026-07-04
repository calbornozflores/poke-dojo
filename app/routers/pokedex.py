import random
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Pokemon, CaughtPokemon, PendingEncounter

router = APIRouter(prefix="/pokedex", tags=["pokedex"])

GEN_NAMES = {
    1: "Kanto",
    2: "Johto",
    3: "Hoenn",
    4: "Sinnoh",
    5: "Unova",
    6: "Kalos",
    7: "Alola",
    8: "Galar",
    9: "Paldea",
}

GEN_SIZES = {1: 151, 2: 100, 3: 135, 4: 107, 5: 156, 6: 72, 7: 88, 8: 96, 9: 120}


def _catch_probability(catch_rate: int, final_score: float) -> float:
    hp_fraction = (100.0 - final_score) / 100.0
    a = (3.0 - 2.0 * hp_fraction) * catch_rate / 255.0
    return max(0.05, min(1.0, a))


@router.get("/data")
def pokedex_data(
    gen: int = Query(..., ge=1, le=9),
    username: str = Query(""),
    db: Session = Depends(get_db),
):
    pokemon_in_gen = db.query(Pokemon).filter(Pokemon.generation == gen).order_by(Pokemon.id).all()

    caught_map: dict[int, CaughtPokemon] = {}
    pending_id: int | None = None
    if username:
        for row in db.query(CaughtPokemon).filter(CaughtPokemon.username == username).all():
            caught_map[row.pokemon_id] = row
        enc = db.query(PendingEncounter).filter(PendingEncounter.username == username).first()
        if enc:
            pending_id = enc.pokemon_id

    result = []
    for p in pokemon_in_gen:
        caught = caught_map.get(p.id)
        result.append({
            "id": p.id,
            "name": p.name,
            "sprite_url": p.sprite_url,
            "caught": caught is not None,
            "level": caught.level if caught else None,
            "caught_at": caught.caught_at.strftime("%Y-%m-%d") if caught else None,
            "is_pending": p.id == pending_id,
        })

    caught_count = sum(1 for r in result if r["caught"])
    return {
        "gen": gen,
        "gen_name": GEN_NAMES[gen],
        "pokemon": result,
        "caught_count": caught_count,
        "total_count": len(result),
    }


@router.get("/encounter")
def get_encounter(username: str = Query(""), db: Session = Depends(get_db)):
    if not username:
        return None
    enc = db.query(PendingEncounter).filter(PendingEncounter.username == username).first()
    if not enc:
        return None
    p = db.query(Pokemon).get(enc.pokemon_id)
    if not p:
        return None

    enc_level = round(enc.final_score)
    owned = db.query(CaughtPokemon).filter_by(username=username, pokemon_id=enc.pokemon_id).first()
    can_catch = (owned is None) or (enc_level > owned.level)
    a = _catch_probability(p.catch_rate or 45, enc.final_score)

    return {
        "pokemon_id": p.id,
        "pokemon_name": p.name,
        "sprite_url": p.sprite_url,
        "level": enc_level,
        "can_catch": can_catch,
        "throws_used": enc.throws_used,
        "throws_remaining": 3 - enc.throws_used,
        "catch_probability": round(a, 4),
        "hp_fraction": round((100.0 - enc.final_score) / 100.0, 4),
    }


class ThrowRequest(BaseModel):
    username: str
    pokemon_id: int


@router.post("/throw")
def throw_pokeball(req: ThrowRequest, db: Session = Depends(get_db)):
    enc = db.query(PendingEncounter).filter_by(
        username=req.username, pokemon_id=req.pokemon_id
    ).first()
    if not enc:
        raise HTTPException(status_code=404, detail="No pending encounter found")

    p = db.query(Pokemon).get(enc.pokemon_id)
    if not p:
        raise HTTPException(status_code=404, detail="Pokémon not found")

    a = _catch_probability(p.catch_rate or 45, enc.final_score)
    caught = random.random() < a

    enc.throws_used += 1
    throws_used = enc.throws_used

    if caught:
        enc_level = round(enc.final_score)
        owned = db.query(CaughtPokemon).filter_by(
            username=req.username, pokemon_id=enc.pokemon_id
        ).first()
        if owned is None:
            db.add(CaughtPokemon(
                username=req.username,
                pokemon_id=enc.pokemon_id,
                level=enc_level,
                attempts_used=throws_used,
            ))
        elif enc_level > owned.level:
            owned.level = enc_level
            owned.caught_at = datetime.utcnow()
            owned.attempts_used = throws_used
        db.delete(enc)
        db.commit()
        return {
            "result": "caught",
            "throws_remaining": 0,
            "catch_probability": round(a, 4),
        }

    if throws_used >= 3:
        db.delete(enc)
        db.commit()
        return {
            "result": "fled",
            "throws_remaining": 0,
            "catch_probability": round(a, 4),
        }

    db.commit()
    return {
        "result": "missed",
        "throws_remaining": 3 - throws_used,
        "catch_probability": round(a, 4),
    }
