"""Topping up the skill list from the game's own master database.

The in-game master database is the source of truth for skill names. The bot
OCRs a skill name off the screen and fuzzy-matches it against this list, so a
skill the list has never heard of cannot be bought and nothing says why. When
the game adds skills - a new umamusume, a new support card - the list needs to
learn them.

Three decisions worth knowing about.

**The user's list lives in `userdata/`, shadowing the one in `resource/`.** The
repository ships a baseline and never receives anyone's updates; a sync writes
only to `userdata/skills.json`, which is gitignored. This is the same shadowing
the project uses for race presets.

**Merging is keyed on the normalised name, not the raw string.** Measured
against the shipped list on 11 Sep 2026: the database held 222 names absent
from it by exact comparison, but only **89** after normalising. The other 133
were punctuation and spacing variants of skills already there. Adding those
would not be harmless - the matcher scores OCR text against every candidate, so
near-duplicates compete with the real entry and make matching worse.

**The database is read read-only and never written.** It is a live game file.
`mode=ro` on the connection URI, and the path the user gives is resolved rather
than trusted to be exact - people know where they installed the game, not which
subfolder Cygames keeps its database in.
"""
import datetime
import json
import os
import re
import sqlite3
import subprocess

import bot.base.log as logger

log = logger.get_logger(__name__)

# The repository's baseline, and the user's own copy which shadows it.
SHIPPED_PATH = os.path.join('resource', 'uma_it', 'skills.json')
USER_PATH = os.path.join('userdata', 'skills.json')

# What the list was built from, shadowed the same way. Kept beside the list
# rather than inside it: the list is a plain array that several things read,
# and a header object would be an entry every one of them has to skip.
META_SHIPPED = os.path.join('resource', 'uma_it', 'skills_meta.json')
META_USER = os.path.join('userdata', 'skills_meta.json')

# Where the chosen master.mdb location is remembered between presses.
CONFIG_PATH = os.path.join('userdata', 'skills_db_source.json')

# text_data categories. Verified against a real master.mdb on 11 Sep 2026:
# category 47 joins all 714 rows of skill_data, category 48 holds descriptions.
CAT_SKILL_NAME = 47
CAT_SKILL_DESC = 48

# Tried in order when the user has not chosen a location yet. The game keeps
# its database under LocalLow regardless of where the client itself installs,
# so this is usually enough and the picker never has to appear.
DEFAULT_CANDIDATES = (
    os.path.expandvars(r"%USERPROFILE%\AppData\LocalLow\Cygames\Umamusume\master\master.mdb"),
    os.path.expandvars(r"%USERPROFILE%\AppData\LocalLow\Cygames\umamusume\master\master.mdb"),
)

# How deep to look under a folder the user picked. They are asked for the
# install folder, and master.mdb sits a couple of levels down from anything
# they would recognise as one.
MAX_SEARCH_DEPTH = 4


# Grade symbols the game suffixes onto a skill name, and the characters OCR
# renders them as. Measured on a real master.mdb: 153 of 612 names end in one
# of these, and **not one of them has an un-suffixed twin in the database** - so
# `Corner Acceleration ○` and a list's `Corner Acceleration` are one skill under
# two spellings, not two skills. Merging without stripping them adds a second
# candidate for every OCR read of those 153.
_GRADE_SYMBOLS = '○◎×〇'
_GRADE_AS_OCR = ('o', 'x', '0')


def merge_key(name: str) -> str:
    """The identity two spellings of one skill share.

    `normalize_text_for_match` alone is not enough: it strips punctuation, and a
    grade symbol survives as a letter. OCR makes this worse by reading ○ as a
    capital O, which is how the bot's own logs spell it.
    """
    from uma_it.parse import normalize_text_for_match
    text = (name or '').strip()
    while text and text[-1] in _GRADE_SYMBOLS:
        text = text[:-1].strip()
    parts = normalize_text_for_match(text).split()
    if len(parts) > 1 and parts[-1] in _GRADE_AS_OCR:
        parts = parts[:-1]
    return ' '.join(parts)


def active_path() -> str:
    """The skills file in force: the user's if they have one, else the repo's."""
    return USER_PATH if os.path.isfile(USER_PATH) else SHIPPED_PATH


def load_all() -> list:
    """Every skill record in the active list."""
    try:
        with open(active_path(), 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception as e:
        log.warning(f"Could not read the skill list at {active_path()}: {e}")
        return []


def save_all(skills: list) -> None:
    """Write the skill list, always to userdata - never back into resource."""
    os.makedirs(os.path.dirname(USER_PATH), exist_ok=True)
    with open(USER_PATH, 'w', encoding='utf-8') as f:
        # ensure_ascii=False: skill names carry ♪, ○, × and accented letters.
        json.dump(skills, f, ensure_ascii=False, indent=1)


def game_version() -> str:
    """The installed client's version, or '' when it cannot be asked.

    `master.mdb` carries no version of its own - there is no version table in
    it - so the number a user would recognise has to come from the package
    manager on the device. Best-effort: the list is still correct without it,
    and a sync must not fail because the emulator is closed.
    """
    try:
        adb = os.path.join('deps', 'adb', 'adb.exe')
        if not os.path.isfile(adb):
            return ''
        device = ''
        try:
            import config
            device = ((config.CONFIG or {}).get('bot', {}).get('auto', {})
                      .get('adb', {}).get('device_name', '')) or ''
        except Exception:
            pass
        cmd = [adb] + (['-s', device] if device else []) + [
            'shell', 'dumpsys', 'package', 'com.cygames.umamusume']
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        m = re.search(r'versionName=(\S+)', out.stdout or '')
        return m.group(1) if m else ''
    except Exception as e:
        log.debug(f"Could not read the game version: {e}")
        return ''


def read_meta() -> dict:
    """What the active list was built from - the user's note, else the repo's."""
    for path in (META_USER, META_SHIPPED):
        # Only the note that belongs to the list in force.
        if path == META_USER and active_path() != USER_PATH:
            continue
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            continue
    return {}


def write_meta(mdb_path: str, count: int, action: str) -> dict:
    """Record what the list was just built from, beside the list itself."""
    try:
        stamp = datetime.datetime.fromtimestamp(
            os.path.getmtime(mdb_path)).strftime('%Y-%m-%d')
    except Exception:
        stamp = ''
    meta = {
        'game_version': game_version(),
        'master_mdb_date': stamp,
        'skills': count,
        'updated': datetime.date.today().isoformat(),
        'action': action,
    }
    try:
        os.makedirs(os.path.dirname(META_USER), exist_ok=True)
        with open(META_USER, 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=1)
    except Exception as e:
        log.warning(f"Could not record the skill list version: {e}")
    return meta


def remembered_source() -> str:
    """The master.mdb path the user chose last time, or ''."""
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return str(json.load(f).get('master_mdb') or '')
    except Exception:
        return ''


def remember_source(path: str) -> None:
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump({'master_mdb': path}, f, ensure_ascii=False, indent=1)


def _is_master_mdb(path: str) -> bool:
    """True when this really is the game's database.

    Checked by opening it rather than by name: a file called master.mdb that
    is not one should fail here and not halfway through a sync.
    """
    if not os.path.isfile(path):
        return False
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            names = {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            return {'skill_data', 'text_data'} <= names
        finally:
            con.close()
    except Exception:
        return False


def resolve(hint: str = '') -> str:
    """Find master.mdb from whatever the user gave, or '' if it is not there.

    Accepts the file itself, the folder holding it, or any folder above it
    within `MAX_SEARCH_DEPTH` - the user is asked for an install folder, which
    is not where Cygames puts the database.
    """
    hint = (hint or '').strip().strip('"')
    if hint:
        if _is_master_mdb(hint):
            return hint
        direct = os.path.join(hint, 'master.mdb')
        if _is_master_mdb(direct):
            return direct
        if os.path.isdir(hint):
            root_depth = hint.rstrip(os.sep).count(os.sep)
            for dirpath, dirnames, filenames in os.walk(hint):
                if dirpath.count(os.sep) - root_depth >= MAX_SEARCH_DEPTH:
                    dirnames[:] = []
                    continue
                if 'master.mdb' in filenames:
                    found = os.path.join(dirpath, 'master.mdb')
                    if _is_master_mdb(found):
                        return found
        return ''

    for candidate in (remembered_source(),) + DEFAULT_CANDIDATES:
        if candidate and _is_master_mdb(candidate):
            return candidate
    return ''


def read_game_skills(mdb_path: str) -> list:
    """Every skill the game knows, as records shaped like the list's own."""
    con = sqlite3.connect(f"file:{mdb_path}?mode=ro", uri=True)
    try:
        rows = con.execute(
            'SELECT n.text, d.text, s.rarity '
            'FROM skill_data s '
            'JOIN text_data n ON n.category=? AND n."index"=s.id '
            'LEFT JOIN text_data d ON d.category=? AND d."index"=s.id',
            (CAT_SKILL_NAME, CAT_SKILL_DESC)).fetchall()
    finally:
        con.close()

    out, seen = [], set()
    for name, desc, rarity in rows:
        name = (name or '').strip()
        if not name or name in seen:
            continue
        seen.add(name)
        out.append({
            'skill_id': 'G_' + name.replace(' ', '-'),
            'name': name,
            'tier': 'A',
            'skill_type': 'Others',
            'prerequisite_of': [],
            'prerequisites': [],
            'description': (desc or '').strip(),
            'purchase_option': 'Direct',
            # skill_data.rarity is an integer; 1 is the ordinary kind.
            'rarity': 'Normal' if rarity in (None, 1) else 'Rare',
        })
    return out


# A database returning fewer than this is not a database worth pruning
# against. Prune deletes, so it refuses rather than emptying the list on a
# half-read file.
MIN_CREDIBLE_SKILLS = 200


def prune(hint: str = '') -> dict:
    """Drop entries for skills the game does not have.

    The shipped list came from a scrape and carries names the game never uses -
    1,089 of 1,610 when this was written. They are not free: the matcher scores
    an OCR'd name against every candidate, so a name the game cannot show can
    still win a frame. `'Speed Star'` resolved to `'α-star*'` that way.

    Kept by `merge_key`, not by exact name, so an un-suffixed alias of a graded
    skill survives - `Corner Acceleration` is what OCR produces for the game's
    `Corner Acceleration ○`, and dropping it would lose a spelling that occurs.
    """
    from uma_it.parse import reset_skills_database_cache

    mdb = resolve(hint)
    if not mdb:
        return {'ret': 1, 'msg': 'master.mdb not found'}
    try:
        game = read_game_skills(mdb)
    except Exception as e:
        return {'ret': 1, 'msg': f'could not read the database: {e}'}
    if len(game) < MIN_CREDIBLE_SKILLS:
        log.warning(f"Refusing to prune against {len(game)} skills from {mdb}")
        return {'ret': 1,
                'msg': f'the database returned only {len(game)} skills; not pruning'}

    keys = {merge_key(s['name']) for s in game}
    keys.discard('')
    existing = load_all()
    kept = [s for s in existing if merge_key(s.get('name', '')) in keys]
    removed = [s.get('name', '') for s in existing
               if merge_key(s.get('name', '')) not in keys]

    if removed:
        save_all(kept)
        reset_skills_database_cache()
    remember_source(mdb)
    meta = write_meta(mdb, len(kept), 'pruned')
    log.info(f"Skill list pruned against {mdb}: {len(removed)} removed, "
             f"{len(kept)} kept (game {meta.get('game_version') or '?'})")
    return {'ret': 0, 'source': mdb, 'removed': removed,
            'removed_count': len(removed), 'total': len(kept), 'meta': meta}


def sync(hint: str = '') -> dict:
    """Add skills the game knows and the list does not.

    Never removes anything. The shipped list carries names from other sources
    that the database does not have, and deciding those are wrong is a
    different job from learning new ones.
    """
    # Imported here rather than at module scope: parse.py imports this module
    # for `active_path`, so a top-level import each way would be a cycle.
    from uma_it.parse import reset_skills_database_cache

    mdb = resolve(hint)
    if not mdb:
        tried = [p for p in ((hint,) if hint else (remembered_source(),) + DEFAULT_CANDIDATES) if p]
        log.warning(f"master.mdb not found. Tried: {tried}")
        return {'ret': 1, 'msg': 'master.mdb not found', 'tried': tried}

    try:
        game = read_game_skills(mdb)
    except Exception as e:
        log.warning(f"Could not read {mdb}: {e}")
        return {'ret': 1, 'msg': f'could not read the database: {e}', 'tried': [mdb]}

    existing = load_all()
    known = {merge_key(s.get('name', '')) for s in existing}
    known.discard('')

    added = []
    for skill in game:
        key = merge_key(skill['name'])
        if not key or key in known:
            continue
        known.add(key)
        existing.append(skill)
        added.append(skill['name'])

    if added:
        save_all(existing)
        # The loader keeps the names in a module-level cache, so without this
        # the running bot goes on matching against the old list until the next
        # restart - and the button looks like it did nothing.
        reset_skills_database_cache()

    # The spark vocabulary comes out of the same file and goes stale for the
    # same reason, so one press keeps both current. Separate list, separate
    # namespace - see uma_it/spark_db.py.
    from uma_it import spark_db
    sparks = spark_db.sync_from(mdb)

    remember_source(mdb)
    meta = write_meta(mdb, len(existing), 'synced')
    meta['sparks'] = sparks['total']
    log.info(f"Skill list synced from {mdb}: {len(added)} new, "
             f"{len(existing)} total (game {meta.get('game_version') or '?'})")
    return {'ret': 0, 'source': mdb, 'added': added,
            'added_count': len(added), 'total': len(existing), 'meta': meta,
            'sparks_added': sparks['added_count'], 'sparks_total': sparks['total']}
