# poke-dojo

A local Pokémon quiz app with five Dojo game modes, a Battle Arena (VS Mode + Solo Challenge), leaderboard, personal profile with XGBoost AI analysis, and a Trainer Journey chart.

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
  main.py            FastAPI app entry point + page routes
  database.py        SQLAlchemy engine and safe migrations
  models.py          ORM models: Pokemon, User, GameResult, EvoScoreHistory,
                       CompetitiveMatch, CompetitiveResult
  routers/
    game.py          /game/start, /game/submit, /game/profile/breakdown
    scores.py        /scores/leaderboard (Dojo, per-mode tabs)
    journey.py       /journey/history (EVO score over time)
    battle_arena.py  /battle/match/*, /battle/round/*, /battle/leaderboard
    challenge.py     /challenge/train (legacy)
  services/
    data_loader.py   Background PokeAPI fetch with progress
    string_match.py  rapidfuzz accuracy for Name It
    pokemon_data.py  Random / Professor Oak Pokémon selection
    shadow_model.py  Per-user Shadow model for Solo Challenge
    xgboost_model.py Per-user XGBoost + SHAP category analysis
  templates/         Jinja2 HTML (base, index, game, scores, profile,
                       trainer_journey, battle_arena, arena_leaderboard, loading)
data/
  fetch_data.py      One-time PokeAPI → SQLite population script
  pokemon.db         SQLite database (git-ignored)
static/
  css/style.css
  js/game1.js game2.js
```

## Game modes

### Dojo (5 modes)
- **Name It — Medium**: full artwork shown, type the Pokémon name
- **Name It — Hard**: silhouette only, identify from outline
- **Guess the Number**: name + artwork shown, enter the Pokédex number
- **Guess the Type — Easy**: pick primary type from 4 choices
- **Guess the Type — Hard**: toggle all types from 18 options, then submit

### Battle Arena
- **VS Mode**: 2 players, same keyboard. Silhouette reveals over 10s. P1 = Q/W/E, P2 = I/O/P.
- **Solo Challenge**: endless rounds, 3 Luvdisc lives, custom key bindings, tightening timer. Your Shadow (trained on your response times) competes against you.

## Key design decisions

- **No auth**: username-only sessions via browser localStorage. Server upserts users by name.
- **Professor Oak Analysis**: unlocks after 20 games per mode. XGBoost trains per-user; picks hardest-predicted Pokémon 80% of the time.
- **EVO score**: exponential moving average of final scores, tracked across all games and charted on Trainer Journey.
- **SHAP bars in Profile**: AI bars sort categories hardest-first (positive SHAP = hard, negative = easy). Falls back to accuracy sort when model not yet trained.
- **Same-letter options in Arena**: wrong-answer options prefer the same first letter as the correct Pokémon (SQLAlchemy `ilike` query).
- **Shadow model**: per-user rolling average of response times per Pokémon ID, stored in `data/shadow_model_{username}.json`.
- **Data**: fetched from PokeAPI once, cached in SQLite. Sprites served via PokeAPI CDN — no local download.
- **Accuracy formulas**:
  - Name It: `rapidfuzz.fuzz.ratio(guess, answer)` → 0–100
  - Guess Number: `max(0, 100 * (1 - |guess - actual| / 1025))`
  - Type Easy/Hard: exact match / partial credit

## Sprite conventions

- Official artwork: `https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/{id}.png`
- Pixel sprites: `https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{id}.png`
- Notable IDs: Metapod=#11 (VS Mode icon), Mewtwo=#150 (Solo icon), Gastly=#92 (game-over art), Luvdisc=#370 (lives), Slaking=#289 (win art)

## Running data fetch

The fetch script is idempotent — safe to re-run. It pulls all 1025 Pokémon from PokeAPI including base stats, evolution stage, generation, and sprite URLs.
