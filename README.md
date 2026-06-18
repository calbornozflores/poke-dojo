# Poke-Dojo <img src="https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/107.png" height="32" align="absmiddle">

A local Pokémon quiz app with five Dojo game modes, a timed scoring system, a leaderboard, a personal profile with AI-powered breakdown, and a **Trainer Journey** page to track your EVO score over time. After 20 games, **Professor Oak Analysis** activates automatically — using machine learning to serve the Pokémon most likely to stump you. Plus a **Battle Arena** with VS Mode (2 players, same keyboard) and Solo Challenge (endless, custom keys, tightening timer, and a personal Shadow that learns your response times). Sign in with Google to claim a unique trainer name and compete on the **Global Leaderboard** — your Solo Challenge best score is synced to a shared cloud ranking visible to all players worldwide.

---

## Screenshots

### Welcome Screen
Sign in with Google to claim a unique trainer name shared across all instances of the app — or skip auth and play as a local guest. Your session is saved in the browser. Includes a fan-game disclaimer crediting Nintendo, Game Freak, and The Pokémon Company.

![Home](screenshots/01_home.png)

### Game Intro Screen
Each mode begins with a brief intro explaining the rules, scoring formula, and controls. Battle Arena buttons show Metapod sprites (VS Mode) and Mewtwo (Solo Challenge) inline with the mode name.

![Intro Screen](screenshots/02_play_intro.png)

### Name It — Easy
Full artwork shown. Pick the correct name from three choices — click a button or press Q / W / E.

![Name It Easy](screenshots/03b_play_nameit_easy.png)

### Name It — Medium
A Pokémon appears with full artwork. Type its name as fast as you can — speed matters for your score.

![Name It Medium](screenshots/03_play_nameit.png)

### Name It — Hard (Silhouette)
Only the black silhouette is shown. Identify the Pokémon from its outline alone.

![Name It Hard intro](screenshots/04_play_nameit_hard_intro.png)
![Name It Hard game](screenshots/05_play_nameit_hard.png)

### Result Screen
After each answer: accuracy ring, **final score in pts** (accuracy × time bonus), and your current **EVO score**.

![Result](screenshots/06_play_result.png)

### Guess the Number
The Pokémon's name and artwork are shown. Enter its Pokédex number — the closer the better.

![Guess Number intro](screenshots/07_play_guessnumber_intro.png)
![Guess Number game](screenshots/08_play_guessnumber.png)

### Guess the Type — Easy
Pick the primary type from four choices. Click immediately to save time.

![Type Easy intro](screenshots/09_play_typeeasy_intro.png)
![Type Easy game](screenshots/10_play_typeeasy.png)

### Guess the Type — Hard
Toggle all types this Pokémon has (up to 2) from all 18 options, then submit.

![Type Hard](screenshots/11_play_typehard.png)

### Leaderboard
**All Modes** tab (Snorlax sprite) aggregates scores across all Dojo game modes. Per-mode tabs show Name It (Easy / Medium / Hard), Guess Number, and Guess the Type (Easy / Hard) individually. All scores are in pts (not raw accuracy).

![Leaderboard](screenshots/12_leaderboard.png)

### My Profile
Categorical breakdown by generation, evolution stage, and type. Tabs are ordered Easy → Medium → Hard for Name It modes. The page defaults to **Name Easy** on first visit and remembers your last selected tab for the rest of the session. After 20 games, AI (SHAP) bars appear and become the sort key — orange bars (HARD ↑) rise to the top, blue bars (EASY ↓) sink to the bottom. Falls back to accuracy sort before the model trains.

![My Profile](screenshots/13_profile.png)

### Trainer Journey
Your EVO score — a smoothed measure of long-term skill growth — plotted over every game. Caterpie at the bottom (0), Arceus at the top (100).

![Trainer Journey](screenshots/14_trainer_journey.png)

### Battle Arena — VS Mode Setup
Two trainers enter their names and choose a round count. P1 uses Q/W/E, P2 uses I/O/P. Metapod sprites flank the title.

![VS Mode Setup](screenshots/15_battle_arena_vs_setup.png)

### Battle Arena — VS Round
Official artwork shown as a white silhouette that starts fading in at 35% of the timer. Both players race to press their key first. Once a player locks in, a green **✓** appears next to their name in the scoreboard — but their chosen option stays hidden so the opponent can't copy the answer.

![VS Round](screenshots/17_battle_arena_vs_round.png)

### Battle Arena — Round Result
After both players answer: animated score bars, ✓/✗ per player, and a 5-second countdown to the next round.

![VS Round Result](screenshots/18_battle_arena_vs_result.png)

### Battle Arena — Solo Challenge Setup
Assign any three keys to the three options (Enter, Escape and Space are reserved). Mewtwo sprite marks the title. Three Luvdisc hearts are your lives.

![Solo Setup](screenshots/16_battle_arena_solo_setup.png)

### Battle Arena — Solo Round
Endless mode with custom keys (A/S/D shown). Timer tightens every 10 rounds — from 10s down to 5s at round 50.

![Solo Round](screenshots/19_battle_arena_solo_round.png)

### Battle Arena — Solo Game Over
Three wrong answers, timeouts, or being beaten by Your Shadow ends the run. Gastly's official artwork marks the screen. Analytics show a response-time chart and slowest Pokémon categories.

![Solo Game Over](screenshots/20b_solo_gameover.png)

### Battle Arena — Match End
Trophy, winner, final scores, and a round-by-round recap. Rematch starts a fresh match with the same settings.

![Match End](screenshots/20_battle_arena_match_end.png)

### Battle Arena — Leaderboard
Solo Challenge and VS Mode rankings in a shared leaderboard. A **🌐 Global** tab appears when Supabase is configured — showing the worldwide Solo Challenge ranking (one best score per Google account). Accessible from the Leaderboard nav dropdown.

![Arena Leaderboard](screenshots/21_arena_leaderboard.png)

---

## Installation

### Requirements
- Python 3.12+
- [uv](https://astral.sh/uv/) — fast Python package manager

**Install uv:**
```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### OS-specific prerequisite

**macOS** — XGBoost requires OpenMP, which Apple Clang does not include:
```bash
brew install libomp
```

**Linux (Debian / Ubuntu)** — most desktop installs already have this; only needed on minimal/server images:
```bash
sudo apt install libgomp1
# Fedora / RHEL: sudo dnf install libgomp
```

**Windows** — no extra step needed. XGBoost ships pre-built wheels that bundle the runtime.

### Setup

```bash
# 1. Clone the repo
git clone https://github.com/calbornozflores/poke-dojo.git
cd poke-dojo

# 2. Install dependencies
uv sync
```

---

## Running

```bash
uv run uvicorn app.main:app --reload
```

Open **http://localhost:8000**.

**First run:** the app automatically fetches all 1025 Pokémon from PokéAPI in the background (~3–4 min). Subsequent starts are instant.

**Optional — pre-fetch before starting:**
```bash
uv run python data/fetch_data.py
```

---

## How to Play

### <img src="https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/172.png" height="22" align="absmiddle"> <img src="https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/25.png" height="22" align="absmiddle"> Name It
- **Easy** — full artwork shown, pick the correct name from three choices. Click or press Q / W / E.
- **Medium** — full artwork shown, name hidden. Type the name and press Enter.
- **Hard** — only the silhouette is shown. Identify from the outline alone.

### <img src="https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/493.png" height="22" align="absmiddle"> Guess the Number
Artwork and name shown. Enter the Pokédex number (1–1025). The closer, the better.

### <img src="https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/133.png" height="22" align="absmiddle"> Guess the Type
- **Easy** — pick the primary type from 4 choices (click to submit instantly).
- **Hard** — toggle all types from 18 options, then submit.

### Scoring
Every round has a **60-second countdown timer**.

```
FinalScore = (Accuracy / 100) × max(0, 100 − (TimeUsed / 60) × 100)
```

| Time used | Time bonus | Perfect name score |
|---|---|---|
| 0 s | 100 | 100 pts |
| 15 s | 75 | 75 pts |
| 30 s | 50 | 50 pts |
| 60 s | 0 | 0 pts |

A score ≥ 80 accuracy counts toward your streak.

### Professor Oak Analysis
Unlocks automatically per mode after **20 games**. No checkbox — it's always on once unlocked. The XGBoost model trained on your history picks the Pokémon it predicts you'll find hardest:
- **80%** of rounds: hardest-predicted Pokémon from your weak spots
- **20%** of rounds: completely random, for variety

### EVO Score
An exponential moving average of your final scores, tracked across all games:

```
EVOₜ = min(100, 0.12 × adjusted + 0.88 × EVOₜ₋₁)
```

Where `adjusted = min(100, FinalScore × 1.15)` when Professor Oak is active (challenge bonus), else `adjusted = FinalScore`. Starts at your first game score, approaches 100 as you improve.

### My Profile
Accuracy breakdown by generation ("Gen I • Kanto"), evolution stage, and type. Categories with fewer than 5 games are hidden. After 20 games, AI (SHAP) bars appear and **become the primary sort key**:
- **Orange bar (HARD ↑)** — Professor Oak predicts this category will stay hard for you; floats to the top
- **Blue bar (EASY ↓)** — Professor Oak predicts this category will be easy; sinks to the bottom
- Before 20 games, categories are sorted by accuracy (lowest first)

### Trainer Journey
A smooth SVG chart of your EVO score history. Filter by game mode with the tabs at the top. Defaults to **All Modes** on first visit and remembers your last selected tab for the rest of the session.

### <img src="https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/249.png" height="22" align="absmiddle"> Battle Arena

#### VS Mode
Two players share the same keyboard. Official artwork is shown as a white silhouette that begins revealing at 35% of the timer and is fully visible at time-up. First to press the correct key wins the round.

| Player | Keys |
|---|---|
| Player 1 | Q / W / E → Options 1 / 2 / 3 |
| Player 2 | I / O / P → Options 1 / 2 / 3 |

Once a player answers, a green ✓ appears next to their name in the scoreboard — but their chosen option stays hidden until both have answered, preventing the second player from copying. Score per round = `max(0, floor(time_remaining / 10 × 100))`. After each round a 5-second countdown auto-advances to the next.

#### Solo Challenge
Assign any 3 keys to the options (Enter, Escape and Space are reserved). Endless rounds with 3 Luvdisc lives — a wrong answer, timeout, or being slower than **Your Shadow** removes one. Timer starts at 10s and tightens by 1s every 10 rounds (floor 5s at round 50). Your Shadow learns your average response time per Pokémon and grows faster as you improve.

#### Global Leaderboard
Sign in with Google once, claim a unique trainer name, and your best Solo Challenge run is automatically synced to a shared global ranking. Only your personal best score is kept — the leaderboard always reflects your peak performance. Trainer names are moderated to block offensive words (English and Chilean Spanish) including leet-speak substitutions (e.g. `p3rr4`).

> **Optional — self-hosting with global features:** set `SUPABASE_URL`, `SUPABASE_ANON_KEY`, and `SUPABASE_SERVICE_KEY` in a `.env` file (see `.env.example`). Without these variables the app runs fully offline with no Google auth.

---

## Project Structure

```
poke-dojo/
├── app/
│   ├── main.py               # FastAPI app, startup, page routes
│   ├── database.py           # SQLAlchemy engine + safe migrations
│   ├── models.py             # Pokemon, User, GameResult, EvoScoreHistory,
│   │                         #   CompetitiveMatch, CompetitiveResult
│   ├── routers/
│   │   ├── game.py           # /game/start, /game/submit, /game/profile/breakdown
│   │   ├── scores.py         # /scores/leaderboard (Dojo, per-mode tabs)
│   │   ├── journey.py        # /journey/history (EVO score chart data)
│   │   ├── battle_arena.py   # /battle/match/*, /battle/round/*, /battle/leaderboard,
│   │   │                     #   /battle/submit-global-score, /battle/global-leaderboard
│   │   ├── auth.py           # /auth/claim-username, /auth/verify (Google OAuth)
│   │   └── challenge.py      # /challenge/train (legacy)
│   ├── services/
│   │   ├── data_loader.py    # Background PokeAPI fetch with progress
│   │   ├── string_match.py   # rapidfuzz accuracy for Name It
│   │   ├── pokemon_data.py   # Random / Professor Oak Pokémon selection
│   │   ├── shadow_model.py   # Per-user Shadow (response-time rolling average)
│   │   ├── xgboost_model.py  # Per-user XGBoost + SHAP category analysis
│   │   ├── supabase_client.py# Supabase admin + anon client helpers
│   │   └── username_filter.py# Profanity filter (English + Chilean, leet-speak aware)
│   └── templates/            # Jinja2 HTML (base, index, game, scores, profile,
│                             #   trainer_journey, battle_arena, arena_leaderboard,
│                             #   auth_callback, auth_claim)
├── data/
│   ├── fetch_data.py         # Manual pre-fetch script
│   └── pokemon.db            # SQLite database (git-ignored)
├── .env.example              # Supabase env var template + SQL setup instructions
├── screenshots/              # README screenshots
└── static/
    └── css/style.css
```

---

## Tech Stack

| Component | Technology |
|---|---|
| Backend | FastAPI + Uvicorn |
| Database | SQLite via SQLAlchemy ORM |
| String matching | rapidfuzz |
| ML (Professor Oak + Profile) | XGBoost (native SHAP) |
| Global leaderboard + Auth | Supabase (PostgreSQL + Google OAuth) |
| Profanity filter | better-profanity + custom Chilean wordlist |
| Package manager | uv |
| Data source | PokéAPI (pokeapi.co) |
| Frontend | Vanilla JS + CSS (no framework) |
