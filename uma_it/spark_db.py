"""The spark vocabulary: every spark the game can inherit, and its name.

Sparks are not skills. The game keeps them in `succession_factor`, named
through `text_data` category **147**, which is a different namespace from the
skill names in category 47 that `skills_db` exports. Only 147 has the race and
scenario sparks, so `URA Finale` exists here and in no skill list.

`factor_type` separates them, and the bot's own colour classification maps onto
it exactly:

    1  blue      5 stats                       Speed, Stamina, Power, Guts, Wit
    2  pink     10 aptitudes                   Turf, Sprint, Late Surger, ...
    3  green   101 unique skills               '#LookatCurren', '564 Escapades'
    4  white   234 skills                      'Acceleration', "All I've Got"
    5  white    34 races                       'Arima Kinen', 'Champions C.'
    6  white     4 scenarios                   'URA Finale', 'Unity Cup'
    7  white     1 other                       'Carnival Bonus'

`rarity` on each row is the star level, so the same spark appears once per star
level it can reach; this module collapses those into one entry with `max_stars`.

**Why the matching is careful.** A white spark is read by OCR off a crowded
row, and the failures are ugly: dropped leading characters ('/ictoria Mile'),
missing spaces ('BCL.Classic'), and ○ rendered as a capital O. Resolving those
is what makes a spark targetable, and resolving them *wrongly* is worse than
failing - a target matched to the wrong spark hands back a parent without the
spark that was wanted, silently.

So `resolve_name` accepts a fuzzy match only when it is strong (>= 0.90) or
clearly unambiguous (>= 0.82 and beating the runner-up by 0.15). Measured
against all 182 distinct white names the bot has read in real careers: 129
resolve exactly, 2 on letters alone, 50 fuzzily, and **one is rejected** -
'ser Straightaways', a truncation whose top two candidates were 0.01 apart and
neither of which was the right answer ('Late Surger Straightaways ○'). Every
one of eight negative controls - blue names, pink names, a green name, garbage -
is rejected.
"""
import json
import os
import re
import sqlite3
from difflib import SequenceMatcher

import bot.base.log as logger

log = logger.get_logger(__name__)

SHIPPED_PATH = os.path.join('resource', 'uma_it', 'sparks.json')
USER_PATH = os.path.join('userdata', 'sparks.json')

# The category that names a factor. Not 47 - that is the skill namespace, and
# it has no races or scenarios in it.
CAT_FACTOR_NAME = 147

# factor_type -> what the bot sees on screen.
KIND_BY_TYPE = {1: 'blue', 2: 'pink', 3: 'green',
                4: 'skill', 5: 'race', 6: 'scenario', 7: 'other'}

# The kinds that appear as white rows, which are the ones worth targeting by
# name. Blue and pink already have their own targeting; green is a unique skill
# nobody can choose to inherit.
WHITE_KINDS = ('skill', 'race', 'scenario', 'other')

# Acceptance thresholds for a fuzzy read. See the module docstring for what
# each one is holding back.
STRONG_ENOUGH = 0.90
FUZZY_FLOOR = 0.82
RUNNER_UP_MARGIN = 0.15


def active_path() -> str:
    """The vocabulary in force: the user's if they have one, else the repo's."""
    return USER_PATH if os.path.isfile(USER_PATH) else SHIPPED_PATH


def load_all() -> list:
    try:
        with open(active_path(), 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception as e:
        log.warning(f"Could not read the spark vocabulary at {active_path()}: {e}")
        return []


def save_all(sparks: list) -> None:
    """Always to userdata - the repository ships a baseline and keeps it."""
    os.makedirs(os.path.dirname(USER_PATH), exist_ok=True)
    with open(USER_PATH, 'w', encoding='utf-8') as f:
        json.dump(sparks, f, ensure_ascii=False, indent=1)


def read_game_sparks(mdb_path: str) -> list:
    """Every spark the game has, one entry per name with its highest star level."""
    con = sqlite3.connect(f"file:{mdb_path}?mode=ro", uri=True)
    try:
        rows = con.execute(
            'SELECT s.factor_type, n.text, s.rarity '
            'FROM succession_factor s '
            'JOIN text_data n ON n.category=? AND n."index"=s.factor_id',
            (CAT_FACTOR_NAME,)).fetchall()
    finally:
        con.close()

    merged = {}
    for ftype, name, rarity in rows:
        name = (name or '').strip()
        if not name:
            continue
        kind = KIND_BY_TYPE.get(ftype, 'other')
        try:
            stars = max(1, min(3, int(rarity)))
        except Exception:
            stars = 1
        key = (kind, name)
        merged[key] = max(merged.get(key, 0), stars)
    return [{'name': name, 'kind': kind, 'max_stars': stars}
            for (kind, name), stars in
            sorted(merged.items(), key=lambda kv: (kv[0][0], kv[0][1].lower()))]


def _letters(text: str) -> str:
    """Letters and digits only.

    OCR drops spaces as readily as characters - 'After-SchoolStroll',
    'BCL.Classic' - so a comparison that keeps separators sees a different set
    of tokens and misses. This is what `match_spark_target_name` already does
    for blue and pink names.
    """
    return re.sub(r'[^a-z0-9]', '', (text or '').lower())


_index_cache = None
_index_source = None


def _index():
    """{merge_key: name} and {letters: name} over the white vocabulary."""
    global _index_cache, _index_source
    sparks = load_all()
    if _index_cache is not None and _index_source is sparks:
        return _index_cache
    from uma_it.skills_db import merge_key
    by_merge, by_letters = {}, {}
    for entry in sparks:
        if entry.get('kind') not in WHITE_KINDS:
            continue
        name = entry.get('name') or ''
        if not name:
            continue
        by_merge.setdefault(merge_key(name), name)
        by_letters.setdefault(_letters(merge_key(name)), name)
    _index_cache = (by_merge, by_letters)
    _index_source = sparks
    return _index_cache


def reset_cache():
    """Forget the built index, so a synced vocabulary is picked up at once."""
    global _index_cache, _index_source
    _index_cache = None
    _index_source = None


def resolve_name(text: str) -> str:
    """An OCR'd white spark name mapped to the vocabulary, or ''.

    Returning '' is the safe answer and the deliberate one for anything
    ambiguous: a spark that fails to resolve reads as absent, which costs a
    reroll, while one resolved to the wrong spark hands back a parent missing
    what was asked for and says nothing.
    """
    from uma_it.skills_db import merge_key
    by_merge, by_letters = _index()
    if not by_merge:
        return ''
    key = merge_key(text)
    if key in by_merge:
        return by_merge[key]
    plain = _letters(key)
    if not plain:
        return ''
    if plain in by_letters:
        return by_letters[plain]

    best_name, best, second = '', 0.0, 0.0
    for cand, name in by_letters.items():
        score = SequenceMatcher(None, plain, cand).ratio()
        if score > best:
            best, second, best_name = score, best, name
        elif score > second:
            second = score
    if best >= STRONG_ENOUGH or (best >= FUZZY_FLOOR
                                 and best - second >= RUNNER_UP_MARGIN):
        return best_name
    log.debug(f"Spark name {text!r} not resolved "
              f"(best {best:.2f} {best_name!r}, runner-up {second:.2f})")
    return ''


def sync_from(mdb_path: str) -> dict:
    """Add sparks the game has and the vocabulary does not. Never removes."""
    from uma_it.skills_db import merge_key
    try:
        game = read_game_sparks(mdb_path)
    except Exception as e:
        log.warning(f"Could not read the spark table from {mdb_path}: {e}")
        return {'added': [], 'added_count': 0, 'total': len(load_all())}

    existing = load_all()
    known = {(s.get('kind'), merge_key(s.get('name', ''))) for s in existing}
    added = []
    for spark in game:
        key = (spark['kind'], merge_key(spark['name']))
        if key in known:
            continue
        known.add(key)
        existing.append(spark)
        added.append(spark['name'])

    if added:
        existing.sort(key=lambda s: (s.get('kind', ''), (s.get('name') or '').lower()))
        save_all(existing)
        reset_cache()
    log.info(f"Spark vocabulary: {len(added)} new, {len(existing)} total")
    return {'added': added, 'added_count': len(added), 'total': len(existing)}
