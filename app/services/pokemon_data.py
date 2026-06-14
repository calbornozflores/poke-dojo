import random
from sqlalchemy.orm import Session
from app.models import Pokemon


def get_random_pokemon(db: Session, exclude_ids: list[int] | None = None) -> Pokemon | None:
    query = db.query(Pokemon)
    if exclude_ids:
        query = query.filter(Pokemon.id.notin_(exclude_ids))
    ids = [row[0] for row in query.with_entities(Pokemon.id).all()]
    if not ids:
        ids = [row[0] for row in db.query(Pokemon).with_entities(Pokemon.id).all()]
    if not ids:
        return None
    chosen_id = random.choice(ids)
    return db.query(Pokemon).get(chosen_id)


def get_pokemon_by_id(db: Session, pokemon_id: int) -> Pokemon | None:
    return db.query(Pokemon).get(pokemon_id)


def number_accuracy(guess: int, actual: int, total: int = 1025) -> float:
    distance = abs(guess - actual)
    return max(0.0, 100.0 * (1 - distance / total))
