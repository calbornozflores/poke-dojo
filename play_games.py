"""
Play ~75 games via the API to populate profile and journey data.
Run with: uv run python play_games.py
"""
import sys
sys.path.insert(0, ".")

import requests
import random
from app.database import SessionLocal
from app.models import Pokemon

BASE = "http://localhost:8000"
USERNAME = "Claudio"

def get_name(db, pokemon_id: int) -> str:
    p = db.query(Pokemon).filter(Pokemon.id == pokemon_id).first()
    return p.name if p else "pikachu"

def play_name_guess(db, n=40):
    print(f"Playing {n} Name It (medium) games...")
    for i in range(n):
        r = requests.post(f"{BASE}/game/start", json={"username": USERNAME, "game_type": "name_guess"})
        data = r.json()
        pid = data["pokemon_id"]
        correct = get_name(db, pid)
        time_used = random.uniform(3, 45)
        # 75% correct, 25% wrong to get realistic stats
        guess = correct if random.random() < 0.75 else "wrongguess"
        sr = requests.post(f"{BASE}/game/submit", json={
            "username": USERNAME, "pokemon_id": pid,
            "game_type": "name_guess", "guess": guess, "time_used": time_used,
        })
        score = sr.json().get("final_score", 0)
        print(f"  [{i+1}/{n}] #{pid} {correct:<20} → {score:.1f} pts  ({time_used:.1f}s)")

def play_name_hard(db, n=15):
    print(f"Playing {n} Name It (hard) games...")
    for i in range(n):
        r = requests.post(f"{BASE}/game/start", json={"username": USERNAME, "game_type": "name_hard"})
        data = r.json()
        pid = data["pokemon_id"]
        correct = get_name(db, pid)
        time_used = random.uniform(8, 58)
        guess = correct if random.random() < 0.50 else "wrongguess"
        sr = requests.post(f"{BASE}/game/submit", json={
            "username": USERNAME, "pokemon_id": pid,
            "game_type": "name_hard", "guess": guess, "time_used": time_used,
        })
        score = sr.json().get("final_score", 0)
        print(f"  [{i+1}/{n}] #{pid} {correct:<20} → {score:.1f} pts")

def play_number_guess(n=10):
    print(f"Playing {n} Guess Number games...")
    for i in range(n):
        r = requests.post(f"{BASE}/game/start", json={"username": USERNAME, "game_type": "number_guess"})
        data = r.json()
        pid = data["pokemon_id"]
        time_used = random.uniform(4, 40)
        offset = random.randint(-50, 50)
        guess = str(max(1, min(1025, pid + offset)))
        sr = requests.post(f"{BASE}/game/submit", json={
            "username": USERNAME, "pokemon_id": pid,
            "game_type": "number_guess", "guess": guess, "time_used": time_used,
        })
        score = sr.json().get("final_score", 0)
        print(f"  [{i+1}/{n}] #{pid} (guessed {guess}) → {score:.1f} pts")

def play_type_easy(n=10):
    print(f"Playing {n} Type Easy games...")
    for i in range(n):
        r = requests.post(f"{BASE}/game/start", json={"username": USERNAME, "game_type": "type_easy"})
        data = r.json()
        pid = data["pokemon_id"]
        choices = data.get("type_choices", ["Fire", "Water", "Grass", "Normal"])
        time_used = random.uniform(1, 18)
        # 60% chance to pick the correct type (position 0 is correct 25% of time statistically)
        # Just pick randomly from choices for variety
        guess = random.choice(choices)
        sr = requests.post(f"{BASE}/game/submit", json={
            "username": USERNAME, "pokemon_id": pid,
            "game_type": "type_easy", "guess": guess, "time_used": time_used,
        })
        score = sr.json().get("final_score", 0)
        print(f"  [{i+1}/{n}] #{pid} → {score:.1f} pts")

if __name__ == "__main__":
    db = SessionLocal()
    try:
        play_name_guess(db, 40)
        play_name_hard(db, 15)
        play_number_guess(10)
        play_type_easy(10)
    finally:
        db.close()
    print("\nDone! Played 75 games total.")
