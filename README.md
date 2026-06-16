# Poke-Dojo <img src="https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/107.png" height="32" align="absmiddle">

A local Pokémon quiz app with five Dojo game modes, a timed scoring system, a leaderboard, a personal profile, and a **Trainer Journey** page to track your EVO score over time. After 20 games, **Professor Oak Analysis** activates automatically — using machine learning to serve the Pokémon most likely to stump you. Plus a **Battle Arena** with VS Mode (2 players, same keyboard) and Solo Challenge (endless, custom keys, tightening timer).

---

## Screenshots

### Welcome Screen
Enter your trainer name to start — no account needed. Your session is saved in the browser.

![Home](screenshots/01_home.png)

### Game Intro Screen
Each mode begins with a brief intro explaining the rules, scoring formula, and controls.

![Intro Screen](screenshots/02_play_intro.png)

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
Global ranking and per-mode tabs showing scores in pts (not raw accuracy).

![Leaderboard](screenshots/12_leaderboard.png)

### My Profile
Categorical accuracy breakdown by generation, evolution stage, and type — sorted hardest-first. After 20 games, AI (SHAP) bars predict which categories will stay hard.

![My Profile](screenshots/13_profile.png)

### Trainer Journey
Your EVO score — a smoothed measure of long-term skill growth — plotted over every game. Caterpie at the bottom (0), Arceus at the top (100).

![Trainer Journey](screenshots/14_trainer_journey.png)

### Battle Arena — VS Mode Setup
Two trainers enter their names and choose a round count. P1 uses Q/W/E, P2 uses I/O/P.

![VS Mode Setup](screenshots/15_battle_arena_vs_setup.png)

### Battle Arena — VS Round
Official artwork shown as a white silhouette. A progress bar counts down the reveal. Both players race to press their key first.

![VS Round](screenshots/17_battle_arena_vs_round.png)

### Battle Arena — Round Result
After both players answer: animated score bars, ✓/✗ per player, and a 5-second countdown to the next round.

![VS Round Result](screenshots/18_battle_arena_vs_result.png)

### Battle Arena — Solo Challenge Setup
Assign any three keys to the three options (Enter, Escape and Space are reserved). One wrong answer ends the run.

![Solo Setup](screenshots/16_battle_arena_solo_setup.png)

### Battle Arena — Solo Round
Endless mode with custom keys (A/S/D shown). Timer tightens every 10 rounds — from 10s down to 5s at round 50.

![Solo Round](screenshots/19_battle_arena_solo_round.png)

### Battle Arena — Match End
Trophy, winner, final scores, and a round-by-round recap. Rematch starts a fresh match with the same settings.

![Match End](screenshots/20_battle_arena_match_end.png)

### Battle Arena — Leaderboard
Solo Challenge and VS Mode rankings in a shared leaderboard. Accessible from the Leaderboard nav dropdown.

![Arena Leaderboard](screenshots/21_arena_leaderboard.png)

---

## Installation

### Requirements
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (fast Python package manager)
- macOS: `brew install libomp` (required by XGBoost)

### Setup

```bash
# 1. Clone the repo
git clone https://github.com/calbornozflores/poke-dojo.git
cd poke-dojo

# 2. Install dependencies
uv sync

# 3. macOS only — XGBoost needs OpenMP
brew install libomp
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

### <img src="https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/25.png" height="22" align="absmiddle"> Name It
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
Accuracy breakdown by generation ("Gen I • Kanto"), evolution stage, and type — sorted hardest-first. Categories with fewer than 5 games are hidden. After 20 games, dual AI (SHAP) bars appear:
- **Orange bar** — Professor Oak predicts this category will stay hard for you
- **Blue bar** — Professor Oak predicts this category will be easy

### Trainer Journey
A smooth SVG chart of your EVO score history. Filter by game mode with the tabs at the top.

### <img src="https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/249.png" height="22" align="absmiddle"> Battle Arena

#### VS Mode
Two players share the same keyboard. Official artwork is shown as a white silhouette that gradually reveals over 10 seconds. First to press the correct name key wins the round.

| Player | Keys |
|---|---|
| Player 1 | Q / W / E → Options 1 / 2 / 3 |
| Player 2 | I / O / P → Options 1 / 2 / 3 |

Score per round = `max(0, floor(time_remaining / 10 × 100))`. After each round a 5-second countdown auto-advances to the next.

#### Solo Challenge
Assign any 3 keys to the options (Enter, Escape and Space are reserved). Endless rounds — one wrong answer or a timeout ends your run. Timer starts at 10s and tightens by 1s every 10 rounds (floor 5s at round 50).

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
│   │   ├── scores.py         # /scores/leaderboard
│   │   ├── journey.py        # /journey/history
│   │   ├── battle_arena.py   # /battle/match/*, /battle/round/*, /battle/leaderboard
│   │   └── challenge.py      # /challenge/train (legacy)
│   ├── services/
│   │   ├── data_loader.py    # Background PokeAPI fetch with progress
│   │   ├── string_match.py   # rapidfuzz accuracy for Name It
│   │   ├── pokemon_data.py   # Random Pokémon selection
│   │   └── xgboost_model.py  # Per-user XGBoost + SHAP category analysis
│   └── templates/            # Jinja2 HTML (base, index, game, scores, profile,
│                             #   trainer_journey, battle_arena, arena_leaderboard)
├── data/
│   ├── fetch_data.py         # Manual pre-fetch script
│   └── pokemon.db            # SQLite database (git-ignored)
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
| Package manager | uv |
| Data source | PokéAPI (pokeapi.co) |
| Frontend | Vanilla JS + CSS (no framework) |
