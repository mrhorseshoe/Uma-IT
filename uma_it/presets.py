"""Named skill-picking presets, one JSON file each.

A preset is the skill configuration and nothing else: the priority tiers, the
blacklist, and whether to buy only what is listed. It deliberately does not
carry `skip_learn_skill` - that switch is what reveals the skill section in the
first place, so a preset that could turn the feature off would be able to hide
its own controls.

The parent's presets store a flat `selected_skills` list plus a
`skill_assignments` map of skill to priority, because its UI models them that
way. This app models tiers directly, so a preset stores the tiers. Its other
fields have nowhere to land here: `threshold`, `manual_purchase` and
`only_at_end` are settings this app does not have.

Files live in `userdata/skill_presets/`, which is gitignored - presets are the
user's, not the repository's.
"""
import glob
import json
import os
import re

import bot.base.log as logger

log = logger.get_logger(__name__)

FOLDER = os.path.join('userdata', 'skill_presets')

# A preset name becomes a filename. Anything that could walk out of the folder
# or upset the filesystem is replaced rather than rejected, so a name the user
# typed still round-trips to something recognisable.
_UNSAFE = re.compile(r'[^\w \-.()\[\]]+', re.UNICODE)


def safe_name(name: str) -> str:
    """A filename-safe version of a preset name, or '' if nothing survives."""
    cleaned = _UNSAFE.sub('_', (name or '').strip())
    cleaned = cleaned.strip(' .')          # no trailing dots or spaces on Windows
    return cleaned[:60]


def _path(name: str) -> str:
    return os.path.join(FOLDER, safe_name(name) + '.json')


def read_all() -> list:
    """Every saved preset, by name."""
    out = []
    if not os.path.isdir(FOLDER):
        return out
    for path in sorted(glob.glob(os.path.join(FOLDER, '*.json'))):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict) and data.get('name'):
                out.append(normalise(data))
        except Exception as e:
            log.warning(f"Skill preset {os.path.basename(path)!r} could not be "
                        f"read and is being skipped: {e}")
    return out


def normalise(data: dict) -> dict:
    """Coerce a preset into the shape the UI and the task both expect.

    Read with defaults throughout: a preset saved before a field existed is
    still a valid preset, exactly as a task saved before a setting is.
    """
    tiers = data.get('tiers')
    if not isinstance(tiers, list):
        tiers = []
    tiers = [[str(s) for s in tier] for tier in tiers if isinstance(tier, list)]
    while len(tiers) < 3:
        tiers.append([])
    return {
        'name': str(data.get('name', '')),
        'tiers': tiers[:3],
        'blacklist': [str(s) for s in (data.get('blacklist') or [])],
        'only_user_provided': bool(data.get('only_user_provided', False)),
    }


def write(preset: dict) -> str:
    """Save a preset, returning the name it was stored under."""
    name = safe_name(preset.get('name', ''))
    if not name:
        raise ValueError("a preset needs a name")
    os.makedirs(FOLDER, exist_ok=True)
    body = normalise(dict(preset, name=name))
    with open(_path(name), 'w', encoding='utf-8') as f:
        json.dump(body, f, ensure_ascii=False, indent=1)
    log.info(f"Skill preset {name!r} saved "
             f"({sum(len(t) for t in body['tiers'])} skills, "
             f"{len(body['blacklist'])} blacklisted)")
    return name


def delete(name: str) -> bool:
    path = _path(name)
    if os.path.isfile(path):
        os.remove(path)
        log.info(f"Skill preset {safe_name(name)!r} deleted")
        return True
    return False
