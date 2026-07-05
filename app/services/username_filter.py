from __future__ import annotations

import re

# Leet-speak: digit substitutions only (charset is already [a-zA-Z0-9-_])
_LEET = str.maketrans("01345678", "oieasbbt")

_BANNED_ES: frozenset[str] = frozenset({
    # body parts (offensive)
    "pene", "pico", "pija", "verga", "tula",
    "concha", "chucha", "raja", "poto", "teta", "culo",
    # strong insults
    "puta", "perra", "zorra", "huevon", "weon",
    "culiao", "culiado", "aweonao",
    "maricon", "marica",
    "ctm", "csm", "ptm", "stm",
    "conchetumadre", "conchetumare", "conchesumadre",
    "mierda", "cagar", "cagado",
    "ojete", "forro", "hdp", "chocha",
    # slurs / hate
    "mongolo", "retrasado", "sidoso", "nazi", "hitler",
    # other Chilean offensive terms
    "pendejo", "cabron", "huea",
})


def _normalize(s: str) -> str:
    """Lowercase + replace leet digits with their letter equivalents."""
    return s.lower().translate(_LEET)


def is_banned(username: str) -> bool:
    """Return True if username (or its leet-normalised form) is offensive."""
    from better_profanity import profanity

    lower = username.lower()
    normalized = _normalize(username)

    # English profanity check on both forms
    if profanity.contains_profanity(lower) or profanity.contains_profanity(normalized):
        return True

    # Spanish / Chilean substring check on both forms
    for form in (lower, normalized):
        for word in _BANNED_ES:
            if word in form:
                return True

    return False


_EMAIL_RE = re.compile(r'[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}', re.IGNORECASE)


def contains_pii(username: str) -> bool:
    """True if username looks like an email address or a phone/ID-like digit run."""
    if _EMAIL_RE.search(username):
        return True
    # Strip separators so "555-1234" / "555 1234" are also caught, not just raw digit runs
    stripped = re.sub(r'[\s\-.]', '', username)
    return bool(re.search(r'\d{7,}', stripped))


def validate_username(name: str) -> str | None:
    """Single source of truth for username rules. Returns an error message, or None if valid."""
    if len(name) < 3 or len(name) > 20:
        return "Username must be 3–20 characters"
    if not all(c.isalnum() or c in "-_" for c in name):
        return "Only letters, numbers, hyphens, and underscores allowed"
    if name.isdigit():
        return "Username must contain at least one letter"
    if contains_pii(name):
        return "Avoid emails, phone numbers, or ID-like numbers in your username"
    if is_banned(name):
        return "That name is not allowed"
    return None
