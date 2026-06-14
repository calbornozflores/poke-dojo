from rapidfuzz import fuzz


def name_accuracy(guess: str, answer: str) -> float:
    """Return 0–100 similarity between guess and the correct Pokémon name."""
    return fuzz.ratio(guess.strip().lower(), answer.strip().lower())
