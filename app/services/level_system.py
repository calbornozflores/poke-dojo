import math
import random as _random

LEVEL_CURVE_BASE = 1.25
LEVEL_CURVE_EXP = 3
XP_CONST = 1.5
POKEMON_LEVEL_RARITY_K = 2.5
RELATIVE_LEVEL_CAP_OFFSET = 10
MAX_TRAINER_LEVEL = 100

DIFFICULTY_CAPS: dict[str, int] = {
    "name_easy":     30,
    "name_guess":    60,
    "name_hard":    100,
    "number_easy":   30,
    "number_medium": 60,
    "number_guess": 100,
    "type_easy":     30,
    "type_medium":   60,
    "type_hard":    100,
}

UNLOCK_THRESHOLDS: dict[str, int] = {
    "name_easy":     0,
    "name_guess":   10,
    "name_hard":    40,
    "number_easy":   0,
    "number_medium":10,
    "number_guess": 40,
    "type_easy":     0,
    "type_medium":  10,
    "type_hard":    40,
}


def xp_for_level(n: int) -> float:
    return LEVEL_CURVE_BASE * (n ** LEVEL_CURVE_EXP)


def level_from_xp(total_xp: float) -> int:
    if total_xp <= 0:
        return 1
    # Small epsilon before truncation avoids floating-point off-by-one at exact level thresholds
    # (e.g. (125.0 / 1.25) ** (1/3) = 4.9999... without it)
    raw = (total_xp / LEVEL_CURVE_BASE) ** (1.0 / LEVEL_CURVE_EXP) + 1e-9
    return max(1, min(MAX_TRAINER_LEVEL, int(raw)))


def xp_progress_in_current_level(total_xp: float) -> tuple[float, float]:
    current_level = level_from_xp(total_xp)
    floor_xp = xp_for_level(current_level)
    next_floor_xp = xp_for_level(current_level + 1)
    xp_in_level = max(0.0, total_xp - floor_xp)
    level_span = next_floor_xp - floor_xp
    return round(xp_in_level, 1), round(level_span, 1)


def is_mode_unlocked(game_type: str, player_level: int) -> bool:
    return player_level >= UNLOCK_THRESHOLDS.get(game_type, 0)


def generate_pokemon_level(game_type: str, player_level: int, rng=_random) -> int:
    difficulty_cap = DIFFICULTY_CAPS.get(game_type, 100)
    limit = min(difficulty_cap, player_level + RELATIVE_LEVEL_CAP_OFFSET)
    limit = max(limit, 1)
    r = rng.random() ** POKEMON_LEVEL_RARITY_K
    return 1 + math.floor((limit - 1) * r)


def calculate_xp_gain(pokemon_level: int, final_score: float) -> float:
    return (pokemon_level * final_score) / XP_CONST
