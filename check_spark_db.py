"""The spark vocabulary, and the resolver that has to be right or expensive.

A white spark is read by OCR off a crowded row and the damage is ugly: dropped
leading characters, missing spaces, and the game's grade circle coming back as
a capital O. Resolving those is what makes a spark targetable.

Resolving one *wrongly* is the expensive failure, and it is silent - a target
matched to the wrong spark hands back a parent without the spark that was
wanted, and nothing says so. So the assertions here are weighted towards what
the resolver must refuse.
"""
import json
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

from uma_it import spark_db
from uma_it.parse import spark_rows_check

failures = []


def check(label, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'}  {label}{'' if cond else '   ' + detail}")
    if not cond:
        failures.append(label)


print("the vocabulary ships with the project")
vocab = spark_db.load_all()
kinds = {}
for s in vocab:
    kinds[s.get('kind')] = kinds.get(s.get('kind'), 0) + 1
check("it loads", len(vocab) > 300, f"{len(vocab)} entries")
check("every entry has a name, a kind and a star cap",
      all(s.get('name') and s.get('kind') and 1 <= s.get('max_stars', 0) <= 3
          for s in vocab))
check("it holds all five blue stats", kinds.get('blue') == 5, str(kinds))
check("  and all ten pink aptitudes", kinds.get('pink') == 10, str(kinds))
check("  and the white kinds the skill list could never cover",
      kinds.get('race', 0) >= 30 and kinds.get('scenario', 0) >= 4, str(kinds))

# The reason this file exists at all: 'URA Finale' is a scenario spark. It is
# in no skill list, so targeting it needs this namespace.
names = {s['name'] for s in vocab}
check("'URA Finale' is in it", 'URA Finale' in names)
check("  as a scenario spark",
      any(s['name'] == 'URA Finale' and s['kind'] == 'scenario' for s in vocab))

print("\nreading a name off the screen")
# Every one of these is real OCR taken from the bot's own logs.
for ocr, want in (('URA Finale', 'URA Finale'),
                  ('Firm Conditions O', 'Firm Conditions ○'),
                  ('/ictoria Mile', 'Victoria Mile'),
                  ('<ashiwa Kinen', 'Kashiwa Kinen'),
                  ('BCL.Classic', 'JBC L. Classic'),
                  ('Jp-Tempo', 'Up-Tempo'),
                  ('After-SchoolStroll', 'After-School Stroll')):
    got = spark_db.resolve_name(ocr)
    check(f"{ocr!r} resolves", got == want, f"got {got!r}")

print("\nwhat it must refuse")
# An ambiguous read is rejected on purpose. 'ser Straightaways' is a truncation
# whose top two candidates scored 0.01 apart, and neither was the right answer
# ('Late Surger Straightaways ○'). Failing here costs a reroll; guessing here
# costs the parent.
check("an ambiguous truncation is refused",
      spark_db.resolve_name('ser Straightaways') == '',
      spark_db.resolve_name('ser Straightaways'))
for junk in ('Speed', 'Stamina', 'Turf', 'Pace Chaser', 'Triumphant Pulse',
             'qwerty nonsense', 'xxxxxxx', ''):
    check(f"  {junk!r} is not a white spark", spark_db.resolve_name(junk) == '',
          spark_db.resolve_name(junk))

print("\na white spark cannot satisfy a blue or pink target")
# spark_rows_check files anything that is not a blue key under pink, so a white
# row carrying a canonical name would have counted as an aptitude hit.
def row(color, canonical, stars):
    return {'name': canonical, 'canonical': canonical, 'stars': stars,
            'color': color, 'y': 0}

hit = spark_rows_check([row('white', 'Long', 3)], {'Long': 2}, 'or', 3)
check("a white row named like an aptitude is ignored", hit == '', repr(hit))
hit = spark_rows_check([row('pink', 'Long', 3)], {'Long': 2}, 'or', 3)
check("  while the real pink row still hits", hit == 'Long', repr(hit))
hit = spark_rows_check([row('green', 'Speed', 3)], {'Speed': 2}, 'or', 3)
check("  and a green row is ignored too", hit == '', repr(hit))

print("\nthe version note covers the vocabulary too")
from uma_it import skills_db
_meta = {}
try:
    _meta = json.load(open(skills_db.META_SHIPPED, encoding='utf-8'))
except Exception as e:
    check("the shipped note exists", False, str(e))
check("it counts the sparks", _meta.get('sparks') == len(vocab),
      f"note says {_meta.get('sparks')}, vocabulary has {len(vocab)}")

print("\nthe shipped vocabulary and the shipped skill list are different lists")
# Category 147 is not category 47. If these ever became the same export, the
# race and scenario sparks would vanish and nobody would notice until a target
# stopped matching.
skill_names = {s['name'] for s in json.load(
    open(skills_db.SHIPPED_PATH, encoding='utf-8')) if s.get('name')}
race_names = {s['name'] for s in vocab if s['kind'] == 'race'}
check("no race spark is in the skill list",
      not (race_names & skill_names), str(sorted(race_names & skill_names)[:4]))

print(f"\n{len(failures)} failed")
sys.exit(1 if failures else 0)
