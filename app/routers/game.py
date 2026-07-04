import random
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, GameResult, Pokemon, EvoScoreHistory, PendingEncounter, CaughtPokemon
from app.services.string_match import name_accuracy
from app.services.pokemon_data import number_accuracy
from app.services import xgboost_model
from app.services.supabase_client import is_authenticated_user
from app.services.level_system import (
    level_from_xp,
    xp_for_level,
    is_mode_unlocked,
    generate_pokemon_level,
    calculate_xp_gain,
    xp_progress_in_current_level,
    UNLOCK_THRESHOLDS,
)


@dataclass(frozen=True)
class _PkmnCache:
    id: int
    name: str
    type1: Optional[str]
    type2: Optional[str]
    sprite_url: str
    generation: int
    base_experience: int
    catch_rate: int

_pkmn: dict[int, _PkmnCache] = {}

def _ensure_pkmn_loaded(db: Session) -> None:
    if _pkmn:
        return
    for p in db.query(Pokemon).all():
        _pkmn[p.id] = _PkmnCache(p.id, p.name, p.type1, p.type2, p.sprite_url, p.generation, p.base_experience or 100, p.catch_rate or 45)

def _cached_pokemon(pokemon_id: int, db: Session) -> Optional[_PkmnCache]:
    if pokemon_id not in _pkmn:
        p = db.query(Pokemon).get(pokemon_id)
        if p:
            _pkmn[pokemon_id] = _PkmnCache(p.id, p.name, p.type1, p.type2, p.sprite_url, p.generation, p.base_experience or 100, p.catch_rate or 45)
    return _pkmn.get(pokemon_id)

router = APIRouter(prefix="/game", tags=["game"])

CHALLENGE_THRESHOLD = 20

_DIFFICULTY_SCALE: dict[str, tuple[str, float]] = {
    "name_easy":     ("name_it",       30.0),
    "name_guess":    ("name_it",       60.0),
    "name_hard":     ("name_it",      100.0),
    "number_easy":   ("number_guess",  30.0),
    "number_medium": ("number_guess",  60.0),
    "number_guess":  ("number_guess", 100.0),
    "type_easy":     ("guess_type",    30.0),
    "type_medium":   ("guess_type",    60.0),
    "type_hard":     ("guess_type",   100.0),
}

_GEN_RANGES: list[tuple[int, int]] = [
    (1, 151), (152, 251), (252, 386), (387, 493),
    (494, 649), (650, 721), (722, 809), (810, 905), (906, 1025),
]

SESSION_TTL = 3600  # 60 minutes of inactivity before eviction

@dataclass
class _GameSession:
    user_id: int
    game_type: str
    games_played: int
    recent_ids: list
    last_evo_per_difficulty: float
    last_evo_combined: float
    has_evo_per_difficulty: bool
    has_evo_combined: bool
    combined_key: str
    scale_max: float
    last_activity: float
    total_xp: float = 0.0
    player_level: int = 1

_session_store: dict[str, _GameSession] = {}

GEN_LABELS = {
    1: "Gen I • Kanto",   2: "Gen II • Johto",   3: "Gen III • Hoenn",
    4: "Gen IV • Sinnoh", 5: "Gen V • Unova",    6: "Gen VI • Kalos",
    7: "Gen VII • Alola", 8: "Gen VIII • Galar",  9: "Gen IX • Paldea",
}

ALL_TYPES = [
    "normal", "fire", "water", "electric", "grass", "ice",
    "fighting", "poison", "ground", "flying", "psychic", "bug",
    "rock", "ghost", "dragon", "dark", "steel", "fairy",
]


def _upsert_user(username: str, db: Session) -> User:
    user = db.query(User).filter(User.username == username).first()
    if not user:
        user = User(username=username)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def _game_count(user_id: int, game_type: str, db: Session) -> int:
    return (
        db.query(GameResult)
        .filter(GameResult.user_id == user_id, GameResult.game_type == game_type)
        .count()
    )


def _evict_stale_sessions() -> None:
    now = time.time()
    stale = [k for k, s in _session_store.items() if now - s.last_activity > SESSION_TTL]
    for k in stale:
        del _session_store[k]


def _load_session(session_id: str, user_id: int, game_type: str, db: Session, *, total_xp: float = 0.0) -> _GameSession:
    games_played = _game_count(user_id, game_type, db)
    recent_ids = [
        r.pokemon_id
        for r in db.query(GameResult)
        .filter(GameResult.user_id == user_id)
        .order_by(GameResult.timestamp.desc())
        .limit(10)
        .all()
    ]
    combined_key, scale_max = _DIFFICULTY_SCALE.get(game_type, (game_type, 100.0))
    latest_evo = (
        db.query(EvoScoreHistory)
        .filter(EvoScoreHistory.user_id == user_id, EvoScoreHistory.game_type == game_type)
        .order_by(EvoScoreHistory.timestamp.desc())
        .first()
    )
    latest_combined = (
        db.query(EvoScoreHistory)
        .filter(EvoScoreHistory.user_id == user_id, EvoScoreHistory.game_type == combined_key)
        .order_by(EvoScoreHistory.timestamp.desc())
        .first()
    )
    session = _GameSession(
        user_id=user_id,
        game_type=game_type,
        games_played=games_played,
        recent_ids=list(recent_ids),
        last_evo_per_difficulty=latest_evo.evo_score if latest_evo else 0.0,
        last_evo_combined=latest_combined.evo_score if latest_combined else 0.0,
        has_evo_per_difficulty=latest_evo is not None,
        has_evo_combined=latest_combined is not None,
        combined_key=combined_key,
        scale_max=float(scale_max),
        last_activity=time.time(),
        total_xp=total_xp,
        player_level=level_from_xp(total_xp),
    )
    _session_store[f"{session_id}:{game_type}"] = session
    return session


class StartRequest(BaseModel):
    username: str
    game_type: str
    challenge_mode: bool = False
    access_token: str | None = None
    session_id: str | None = None


class StartResponse(BaseModel):
    pokemon_id: int
    sprite_url: str
    artwork_url: str
    name: str | None
    challenge_unlocked: bool
    games_played: int
    type_choices: list[str] = []
    name_choices: list[str] = []
    pokemon_level: int = 1
    player_level: int = 1
    mode_locked: bool = False
    number_range_hint: str | None = None


class SubmitRequest(BaseModel):
    username: str
    pokemon_id: int
    game_type: str
    guess: str
    time_used: float = 30.0
    was_challenge: bool = False  # kept for API compat, now computed server-side
    access_token: str | None = None
    session_id: str | None = None
    pokemon_level: int = 1  # echoed from StartResponse; fallback to 1 for old clients


class SubmitResponse(BaseModel):
    accuracy: float
    final_score: float
    evo_score: float | None
    correct_name: str
    correct_number: int
    distance: int | None
    games_played: int
    challenge_unlocked: bool
    correct_types: list[str] = []
    user_types: list[str] = []
    xp_gained: float = 0.0
    total_xp: float = 0.0
    player_level: int = 1
    player_level_before: int = 1
    leveled_up: bool = False
    newly_unlocked_modes: list[str] = []
    pending_encounter: dict | None = None


_DOJO_GAME_TYPES = frozenset({
    "name_easy", "name_guess", "name_hard",
    "number_easy", "number_medium", "number_guess",
    "type_easy", "type_medium", "type_hard",
})


@router.get("/profile/breakdown")
def profile_breakdown(
    username: str = Query(...),
    game_type: str = Query(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return {"has_data": False, "total_games": 0, "breakdown": None}

    total = (
        db.query(GameResult)
        .filter(GameResult.user_id == user.id, GameResult.game_type == game_type)
        .count()
    )

    if total < 5:
        return {"has_data": False, "total_games": total, "breakdown": None}

    rows = (
        db.query(GameResult, Pokemon)
        .join(Pokemon, GameResult.pokemon_id == Pokemon.id)
        .filter(GameResult.user_id == user.id, GameResult.game_type == game_type)
        .all()
    )

    gen_acc   = defaultdict(list)
    stage_acc = defaultdict(list)
    type_acc  = defaultdict(list)

    for result, poke in rows:
        gen_acc[poke.generation].append(result.accuracy)
        stage_acc[poke.stage].append(result.accuracy)
        type_acc[poke.type1].append(result.accuracy)
        if poke.type2:
            type_acc[poke.type2].append(result.accuracy)

    MIN_N = 5
    _TYPE_IDS = {
        "normal": 1, "fighting": 2, "flying": 3, "poison": 4, "ground": 5,
        "rock": 6, "bug": 7, "ghost": 8, "steel": 9, "fire": 10, "water": 11,
        "grass": 12, "electric": 13, "psychic": 14, "ice": 15, "dragon": 16,
        "dark": 17, "fairy": 18,
    }
    _CDN = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/types/generation-ix/scarlet-violet"
    _STAGE_ORDER  = {"basic": 0, "stage_1": 1, "stage_2": 2}
    _STAGE_LABELS = {"basic": "Basic", "stage_1": "Stage 1", "stage_2": "Stage 2"}

    def _avg(lst): return round(sum(lst) / len(lst), 1)

    by_generation = [
        {"label": GEN_LABELS.get(gen, f"Gen {gen}"), "avg": _avg(accs), "n": len(accs)}
        for gen, accs in sorted(gen_acc.items())
        if len(accs) >= MIN_N
    ]

    by_stage = [
        {"label": _STAGE_LABELS.get(stage, stage), "avg": _avg(accs), "n": len(accs)}
        for stage, accs in sorted(stage_acc.items(), key=lambda x: _STAGE_ORDER.get(x[0], 99))
        if len(accs) >= MIN_N
    ]

    by_type = sorted([
        {
            "label": t.capitalize(),
            "icon":  f"{_CDN}/{_TYPE_IDS[t]}.png",
            "avg":   _avg(accs),
            "n":     len(accs),
        }
        for t, accs in type_acc.items()
        if len(accs) >= MIN_N and t in _TYPE_IDS
    ], key=lambda x: x["avg"])

    return {
        "has_data":    True,
        "total_games": total,
        "breakdown": {
            "by_generation": by_generation,
            "by_stage":      by_stage,
            "by_type":       by_type,
        },
    }


@router.post("/start", response_model=StartResponse)
def start_game(req: StartRequest, db: Session = Depends(get_db)):
    is_auth = is_authenticated_user(req.username, req.access_token)

    _ensure_pkmn_loaded(db)
    if not _pkmn:
        raise HTTPException(status_code=503, detail="No Pokémon data found. Run the fetch script first.")

    user_id: int | None = None
    games_played = 0
    challenge_unlocked = False
    recent_ids: list[int] = []

    player_level = 1
    session = None

    if is_auth:
        sess_key = f"{req.session_id}:{req.game_type}" if req.session_id else None
        session = _session_store.get(sess_key) if sess_key else None
        if session:
            session.last_activity = time.time()
            user_id = session.user_id
            games_played = session.games_played
            challenge_unlocked = games_played >= CHALLENGE_THRESHOLD
            recent_ids = list(session.recent_ids)
            player_level = session.player_level
        else:
            _evict_stale_sessions()
            user = _upsert_user(req.username, db)
            user_id = user.id
            session = _load_session(req.session_id or "", user_id, req.game_type, db, total_xp=user.total_xp)
            games_played = session.games_played
            challenge_unlocked = games_played >= CHALLENGE_THRESHOLD
            recent_ids = list(session.recent_ids)
            player_level = session.player_level

    # Trainer level gating + Pokémon level for Name It, Guess Number, and Type modes
    pokemon_level = 1
    number_range_hint: str | None = None
    _NUMBER_MODES = ("number_easy", "number_medium", "number_guess")
    _TYPE_MODES = ("type_easy", "type_medium", "type_hard")

    if req.game_type in ("name_easy", "name_guess", "name_hard"):
        if not is_mode_unlocked(req.game_type, player_level):
            return StartResponse(
                pokemon_id=0, sprite_url="", artwork_url="", name=None,
                challenge_unlocked=False, games_played=games_played,
                mode_locked=True, player_level=player_level,
            )
        pokemon_level = generate_pokemon_level(req.game_type, player_level)

    # Pokemon selection — pure in-memory, 0 DB reads
    if challenge_unlocked and user_id is not None:
        if random.random() < 0.2:
            candidates = [pid for pid in _pkmn if pid not in recent_ids] or list(_pkmn.keys())
            pokemon_id = random.choice(candidates)
        else:
            hard_ids = xgboost_model.predict_hardest(user_id, req.game_type, db, n=50)
            candidates = [pid for pid in hard_ids if pid not in recent_ids] or hard_ids
            pokemon_id = random.choice(candidates[:20])
    else:
        candidates = [pid for pid in _pkmn if pid not in recent_ids] or list(_pkmn.keys())
        pokemon_id = random.choice(candidates)

    pokemon = _pkmn[pokemon_id]

    # Trainer level gating + hint for Guess Number modes
    if req.game_type in _NUMBER_MODES:
        if not is_mode_unlocked(req.game_type, player_level):
            return StartResponse(
                pokemon_id=0, sprite_url="", artwork_url="", name=None,
                challenge_unlocked=False, games_played=games_played,
                mode_locked=True, player_level=player_level,
            )
        pokemon_level = generate_pokemon_level(req.game_type, player_level)
        if req.game_type == "number_easy":
            r = random.randint(0, 19)
            start = max(1, pokemon.id - r)
            end = min(1025, start + 19)
            number_range_hint = f"{start} – {end}"
        elif req.game_type == "number_medium":
            lo, hi = next(
                (lo, hi) for lo, hi in _GEN_RANGES if lo <= pokemon.id <= hi
            )
            number_range_hint = f"{lo} – {hi}"

    # Trainer level gating + Pokémon level for Type modes
    if req.game_type in _TYPE_MODES:
        if not is_mode_unlocked(req.game_type, player_level):
            return StartResponse(
                pokemon_id=0, sprite_url="", artwork_url="", name=None,
                challenge_unlocked=False, games_played=games_played,
                mode_locked=True, player_level=player_level,
            )
        pokemon_level = generate_pokemon_level(req.game_type, player_level)

    # Build type/name choices
    type_choices: list[str] = []
    name_choices: list[str] = []
    if req.game_type == "type_easy":
        pokemon_types = [t for t in [pokemon.type1, pokemon.type2] if t]
        wrong = [t for t in ALL_TYPES if t not in pokemon_types]
        choices = pokemon_types + random.sample(wrong, 4 - len(pokemon_types))
        random.shuffle(choices)
        type_choices = choices
    elif req.game_type == "type_medium":
        pokemon_types = [t for t in [pokemon.type1, pokemon.type2] if t]
        wrong = [t for t in ALL_TYPES if t not in pokemon_types]
        choices = pokemon_types + random.sample(wrong, 9 - len(pokemon_types))
        random.shuffle(choices)
        type_choices = choices
    elif req.game_type == "type_hard":
        type_choices = list(ALL_TYPES)
    elif req.game_type == "name_easy":
        other_ids = [pid for pid in _pkmn if pid != pokemon.id]
        wrong_ids = random.sample(other_ids, 2)
        choices = [pokemon.name] + [_pkmn[pid].name for pid in wrong_ids]
        random.shuffle(choices)
        name_choices = choices

    show_name = req.game_type in (*_NUMBER_MODES, "type_easy")

    return StartResponse(
        pokemon_id=pokemon.id,
        sprite_url=pokemon.sprite_url,
        artwork_url=f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/{pokemon.id}.png",
        name=pokemon.name if show_name else None,
        challenge_unlocked=challenge_unlocked,
        games_played=games_played,
        type_choices=type_choices,
        name_choices=name_choices,
        pokemon_level=pokemon_level,
        player_level=player_level,
        number_range_hint=number_range_hint,
    )


@router.post("/submit", response_model=SubmitResponse)
def submit_answer(req: SubmitRequest, db: Session = Depends(get_db)):
    is_auth = is_authenticated_user(req.username, req.access_token)

    pokemon = _cached_pokemon(req.pokemon_id, db)
    if not pokemon:
        raise HTTPException(status_code=404, detail="Pokémon not found")

    distance = None
    correct_types: list[str] = []
    user_types: list[str] = []

    if req.game_type in ("name_guess", "name_hard"):
        accuracy = name_accuracy(req.guess, pokemon.name)

    elif req.game_type in ("number_easy", "number_medium", "number_guess"):
        try:
            guess_num = int(req.guess) if req.guess.strip() else 0
        except ValueError:
            raise HTTPException(status_code=422, detail="guess must be an integer for number modes")
        distance = abs(guess_num - pokemon.id)
        accuracy = number_accuracy(guess_num, pokemon.id)

    elif req.game_type == "type_easy":
        pokemon_types = [t.lower() for t in [pokemon.type1, pokemon.type2] if t]
        accuracy = 100.0 if req.guess.lower() in pokemon_types else 0.0
        correct_types = [t for t in [pokemon.type1, pokemon.type2] if t]
        user_types = [req.guess.lower()] if req.guess else []

    elif req.game_type in ("type_hard", "type_medium"):
        selected = [t.strip().lower() for t in req.guess.split(",") if t.strip()]
        pokemon_types = [t.lower() for t in [pokemon.type1, pokemon.type2] if t]
        n_types = len(pokemon_types)
        correct_hits = sum(1 for t in selected if t in pokemon_types)
        wrong_hits = sum(1 for t in selected if t not in pokemon_types)
        accuracy = max(0.0, (correct_hits - wrong_hits) / n_types * 100.0) if n_types > 0 else 0.0
        correct_types = [t for t in [pokemon.type1, pokemon.type2] if t]
        user_types = selected

    elif req.game_type == "name_easy":
        accuracy = 100.0 if req.guess.strip().lower() == pokemon.name.lower() else 0.0

    else:
        raise HTTPException(status_code=422, detail="invalid game_type")

    # Compute final score: accuracy × time_score (both 0-100)
    time_used = max(0.0, min(30.0, req.time_used))
    time_score = max(0.0, 100.0 - (time_used / 30.0) * 100.0)
    final_score = round((accuracy / 100.0) * time_score, 1)

    evo_score = None
    games_played = 0
    challenge_unlocked = False

    xp_gained = 0.0
    total_xp_after = 0.0
    player_level_before = 1
    player_level_after = 1
    leveled_up = False
    newly_unlocked: list[str] = []

    if is_auth:
        # Session lookup — if hit, 0 DB reads for user_id, games_before, EVO values
        sess_key = f"{req.session_id}:{req.game_type}" if req.session_id else None
        session = _session_store.get(sess_key) if sess_key else None

        if session:
            user_id = session.user_id
            games_before = session.games_played
            current_evo_pd = session.last_evo_per_difficulty
            has_evo_pd = session.has_evo_per_difficulty
            current_combined = session.last_evo_combined
            has_evo_combined = session.has_evo_combined
            combined_key = session.combined_key
            scale_max = session.scale_max
        else:
            user = _upsert_user(req.username, db)
            user_id = user.id
            games_before = _game_count(user_id, req.game_type, db)
            combined_key, scale_max = _DIFFICULTY_SCALE.get(req.game_type, (req.game_type, 100.0))
            latest_evo = (
                db.query(EvoScoreHistory)
                .filter(EvoScoreHistory.user_id == user_id, EvoScoreHistory.game_type == req.game_type)
                .order_by(EvoScoreHistory.timestamp.desc())
                .first()
            )
            current_evo_pd = latest_evo.evo_score if latest_evo else 0.0
            has_evo_pd = latest_evo is not None
            latest_combined = (
                db.query(EvoScoreHistory)
                .filter(EvoScoreHistory.user_id == user_id, EvoScoreHistory.game_type == combined_key)
                .order_by(EvoScoreHistory.timestamp.desc())
                .first()
            )
            current_combined = latest_combined.evo_score if latest_combined else 0.0
            has_evo_combined = latest_combined is not None

        was_challenge = games_before >= CHALLENGE_THRESHOLD

        # EVO math (all in-memory after session hit)
        adjusted = min(100.0, final_score * 1.15) if was_challenge else final_score

        if has_evo_pd:
            new_evo = min(100.0, 0.12 * adjusted + 0.88 * current_evo_pd)
        else:
            new_evo = min(100.0, adjusted)
        new_evo = round(new_evo, 2)

        effective_score = adjusted * (scale_max / 100.0)
        if current_combined < scale_max:
            if has_evo_combined:
                new_combined = round(min(0.12 * effective_score + 0.88 * current_combined, scale_max), 2)
            else:
                new_combined = round(min(effective_score, scale_max), 2)
            write_combined = True
        else:
            new_combined = current_combined
            write_combined = False

        # XP gain (Name It, Guess Number, and Guess the Type modes)
        if req.game_type in ("name_easy", "name_guess", "name_hard",
                             "number_easy", "number_medium", "number_guess",
                             "type_easy", "type_medium", "type_hard"):
            current_xp = (
                session.total_xp if session
                else (db.query(User.total_xp).filter(User.id == user_id).scalar() or 0.0)
            )
            player_level_before = level_from_xp(current_xp)
            xp_gained = calculate_xp_gain(pokemon.base_experience, req.pokemon_level, final_score)
            total_xp_after = current_xp + xp_gained
            player_level_after = level_from_xp(total_xp_after)
            leveled_up = player_level_after > player_level_before
            newly_unlocked = [
                mode for mode, threshold in UNLOCK_THRESHOLDS.items()
                if player_level_before < threshold <= player_level_after
            ]

        # Single commit per round (includes XP atomic update for name modes)
        db.add(GameResult(
            user_id=user_id,
            pokemon_id=pokemon.id,
            game_type=req.game_type,
            accuracy=accuracy,
            time_used=time_used,
            final_score=final_score,
            was_challenge=was_challenge,
        ))
        db.add(EvoScoreHistory(
            user_id=user_id,
            game_type=req.game_type,
            evo_score=new_evo,
            final_score=final_score,
        ))
        if write_combined:
            db.add(EvoScoreHistory(
                user_id=user_id,
                game_type=combined_key,
                evo_score=new_combined,
                final_score=final_score,
            ))
        if xp_gained > 0:
            from sqlalchemy import text as _text
            db.execute(
                _text("UPDATE users SET total_xp = total_xp + :delta WHERE id = :uid"),
                {"delta": xp_gained, "uid": user_id},
            )
        db.commit()

        # Update session in-place
        if session:
            session.games_played += 1
            session.recent_ids = (session.recent_ids + [pokemon.id])[-10:]
            session.last_evo_per_difficulty = new_evo
            session.last_evo_combined = new_combined
            session.has_evo_per_difficulty = True
            session.has_evo_combined = True
            session.last_activity = time.time()
            if xp_gained > 0:
                session.total_xp = total_xp_after
                session.player_level = player_level_after

        games_played = games_before + 1
        challenge_unlocked = games_played >= CHALLENGE_THRESHOLD
        evo_score = round(new_combined, 1)

    # Upsert pending encounter for Dojo wins
    pending_encounter_data: dict | None = None
    if final_score > 0 and req.game_type in _DOJO_GAME_TYPES and req.username:
        enc_level = req.pokemon_level
        existing_enc = db.query(PendingEncounter).filter_by(username=req.username).first()
        if existing_enc:
            existing_enc.pokemon_id = pokemon.id
            existing_enc.final_score = final_score
            existing_enc.pokemon_level = enc_level
            existing_enc.throws_used = 0
            existing_enc.created_at = datetime.utcnow()
        else:
            db.add(PendingEncounter(
                username=req.username,
                pokemon_id=pokemon.id,
                final_score=final_score,
                pokemon_level=enc_level,
            ))
        db.commit()

        owned = db.query(CaughtPokemon).filter_by(
            username=req.username, pokemon_id=pokemon.id
        ).first()
        can_catch = (owned is None) or (enc_level > owned.level)
        pending_encounter_data = {
            "pokemon_id": pokemon.id,
            "pokemon_name": pokemon.name,
            "sprite_url": pokemon.sprite_url,
            "level": enc_level,
            "can_catch": can_catch,
        }

    return SubmitResponse(
        accuracy=round(accuracy, 1),
        final_score=final_score,
        evo_score=evo_score,
        correct_name=pokemon.name,
        correct_number=pokemon.id,
        distance=distance,
        games_played=games_played,
        challenge_unlocked=challenge_unlocked,
        correct_types=correct_types,
        user_types=user_types,
        xp_gained=round(xp_gained, 1),
        total_xp=round(total_xp_after, 1),
        player_level=player_level_after,
        player_level_before=player_level_before,
        leveled_up=leveled_up,
        newly_unlocked_modes=newly_unlocked,
        pending_encounter=pending_encounter_data,
    )


@router.get("/player/level")
def player_level_status(username: str = Query(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        xp_needed = round(xp_for_level(2) - xp_for_level(1), 1)
        return {
            "player_level": 1,
            "total_xp": 0.0,
            "xp_current": 0.0,
            "xp_needed": xp_needed,
            "unlocked_modes": [m for m, t in UNLOCK_THRESHOLDS.items() if t == 0],
        }
    lvl = level_from_xp(user.total_xp)
    xp_cur, xp_needed = xp_progress_in_current_level(user.total_xp)
    unlocked = [m for m, t in UNLOCK_THRESHOLDS.items() if lvl >= t]
    return {
        "player_level": lvl,
        "total_xp": round(user.total_xp, 1),
        "xp_current": xp_cur,
        "xp_needed": xp_needed,
        "unlocked_modes": unlocked,
    }
