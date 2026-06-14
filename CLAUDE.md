# poke-dojo

A local Pokémon training web app with two quiz games, a leaderboard, and an XGBoost-powered Challenge Mode.

## Setup

```bash
uv sync
uv run python data/fetch_data.py   # one-time PokeAPI data fetch (~5–10 min, ~1025 Pokémon)
uv run uvicorn app.main:app --reload
```

Open http://localhost:8000

## Package management

Always use `uv` — never `pip` directly.

```bash
uv add <package>          # runtime dependency
uv add --dev <package>    # dev-only dependency
uv sync                   # install from lockfile
```

## Project layout

```
app/
  main.py            FastAPI app entry point
  database.py        SQLAlchemy engine and session
  models.py          ORM models: Pokemon, User, GameResult
  routers/
    game.py          /game/start and /game/submit
    scores.py        /scores leaderboard
    challenge.py     /challenge unlock and next-pokemon
  services/
    string_match.py  rapidfuzz accuracy for Game 1
    pokemon_data.py  random/challenge pokemon selection
    xgboost_model.py per-user difficulty model
  templates/         Jinja2 HTML templates
data/
  fetch_data.py      One-time PokeAPI → SQLite population script
  pokemon.db         SQLite database (git-ignored)
  challenge_model_*.json  Per-user XGBoost model artifacts (git-ignored)
static/
  css/style.css
  js/game1.js game2.js
```

## Key design decisions

- **No auth**: username-only sessions via browser localStorage. Server upserts users by name.
- **Challenge Mode**: unlocks after 20 total games. XGBoost trains per-user on their result log; predicts highest-error Pokémon to queue next.
- **Data**: fetched from PokeAPI once and cached in SQLite. Sprites served via PokeAPI CDN URLs — no local download.
- **Game 1 accuracy**: `rapidfuzz.fuzz.ratio(guess, answer)` → 0–100.
- **Game 2 accuracy**: `max(0, 100 * (1 - |guess - actual| / 1025))`.

## Running data fetch

The fetch script is idempotent — safe to re-run. It pulls all 1025 Pokémon from PokeAPI including base stats, evolution stage, generation, and sprite URLs.
