from __future__ import annotations

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
