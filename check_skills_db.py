"""Topping the skill list up from the game database.

Three things here are worth asserting, and one of them is the whole point.

**The merge keys on the normalised name.** Measured against a real master.mdb
on 11 Sep 2026, the database held 222 names the shipped list did not have by
exact comparison and 74 after normalising. The other 148 were punctuation and
spacing variants of skills already there. Adding them would not be harmless:
the matcher scores an OCR'd name against every candidate, so a near-duplicate
competes with the real entry.

**Nothing is ever written into `resource/`.** The repository ships a baseline
and the user's copy shadows it. A sync that wrote back into the tracked file
would put every user's game updates in their working tree.

**The loader's cache is dropped.** It fills once per process, so a sync that
skipped this would write a correct file and change nothing about what the
running bot matches against until the next restart.
"""
import json
import os
import shutil
import sqlite3
import sys
import tempfile

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

from uma_it import skills_db
from uma_it import parse

failures = []


def check(label, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'}  {label}{'' if cond else '   ' + detail}")
    if not cond:
        failures.append(label)


def fake_mdb(path, names):
    """A master.mdb with just the two tables the reader joins."""
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE skill_data (id INTEGER PRIMARY KEY, rarity INTEGER)")
    con.execute('CREATE TABLE text_data (id INTEGER PRIMARY KEY AUTOINCREMENT, '
                'category INTEGER, "index" INTEGER, text TEXT)')
    for i, name in enumerate(names, start=1):
        con.execute("INSERT INTO skill_data (id, rarity) VALUES (?, 1)", (i,))
        con.execute('INSERT INTO text_data (category, "index", text) VALUES (?, ?, ?)',
                    (skills_db.CAT_SKILL_NAME, i, name))
        con.execute('INSERT INTO text_data (category, "index", text) VALUES (?, ?, ?)',
                    (skills_db.CAT_SKILL_DESC, i, f"does {name}"))
    con.commit()
    con.close()


# Run against a temporary userdata so a check never edits the real list.
tmp = tempfile.mkdtemp(prefix="uma_it_skills_")
skills_db.USER_PATH = os.path.join(tmp, 'skills.json')
skills_db.CONFIG_PATH = os.path.join(tmp, 'source.json')
skills_db.SHIPPED_PATH = os.path.join(tmp, 'shipped.json')
with open(skills_db.SHIPPED_PATH, 'w', encoding='utf-8') as f:
    json.dump([{'name': 'Corner Acceleration'}, {'name': 'Straightaway Adept'}], f)

print("the shipped list is used until the user has one of their own")
check("reads the repository's copy first",
      skills_db.active_path() == skills_db.SHIPPED_PATH, skills_db.active_path())

print("\nfinding master.mdb")
mdb = os.path.join(tmp, 'master', 'master.mdb')
os.makedirs(os.path.dirname(mdb))
fake_mdb(mdb, ['Corner Acceleration O', 'Beast Mode', 'Aspire'])
check("the file itself is accepted", skills_db.resolve(mdb) == mdb)
check("so is the folder holding it",
      skills_db.resolve(os.path.dirname(mdb)) == mdb)
check("and a folder above it, which is what a user calls the install folder",
      skills_db.resolve(tmp) == mdb)
check("a path that is not there resolves to nothing",
      skills_db.resolve(os.path.join(tmp, 'nope')) == '')

notdb = os.path.join(tmp, 'decoy', 'master.mdb')
os.makedirs(os.path.dirname(notdb))
with open(notdb, 'w') as f:
    f.write("not a database")
check("a file merely named master.mdb is rejected",
      skills_db.resolve(notdb) == '', skills_db.resolve(notdb))

print("\nthe merge")
parse.reset_skills_database_cache()
res = skills_db.sync(mdb)
check("it reports what it did", res['ret'] == 0, str(res))
# 'Corner Acceleration O' normalises onto the existing 'Corner Acceleration'.
# Exact comparison would have added it, and then two candidates would compete
# for every OCR read of that skill.
check("a punctuation variant of a known skill is not added",
      'Corner Acceleration O' not in res['added'], str(res['added']))
check("  while genuinely new skills are",
      sorted(res['added']) == ['Aspire', 'Beast Mode'], str(res['added']))

print("\nwhere it writes")
check("the user's list now exists", os.path.isfile(skills_db.USER_PATH))
check("  and is what gets read", skills_db.active_path() == skills_db.USER_PATH)
shipped_now = json.load(open(skills_db.SHIPPED_PATH, encoding='utf-8'))
check("  and the shipped list is untouched", len(shipped_now) == 2,
      str(len(shipped_now)))

print("\npressing it again")
res2 = skills_db.sync(mdb)
check("adds nothing the second time", res2['added_count'] == 0, str(res2))
check("  and the location is remembered", skills_db.remembered_source() == mdb,
      skills_db.remembered_source())
res3 = skills_db.sync()
check("  so a later press needs no path at all", res3['ret'] == 0, str(res3))

print("\nthe loader picks the new names up without a restart")
parse.reset_skills_database_cache()
names = parse.load_skills_database()
check("the synced skills are matchable", 'Beast Mode' in names,
      f"{len(names)} names")
parse.skills_database_cache = ['stale']
skills_db.sync(mdb)
check("a sync that adds nothing leaves the cache alone",
      parse.skills_database_cache == ['stale'])
fake_mdb_2 = os.path.join(tmp, 'm2', 'master.mdb')
os.makedirs(os.path.dirname(fake_mdb_2))
fake_mdb(fake_mdb_2, ['Late Surger Savvy'])
skills_db.sync(fake_mdb_2)
check("  but a sync that adds something drops it",
      parse.skills_database_cache is None, str(parse.skills_database_cache))

print("\nthe closest containing name wins, not the first one found")
# Containment used to short-circuit with a break, so a short name that is a
# substring of the query won outright and which one got there first depended on
# set iteration order. Measured against real OCR from live careers: 'Focus'
# resolved to 'Undivided Focus', 'Steadfast' to 'Steadfast Spirit', and
# 'Speed Star' - one of the owner's own priority targets - to 'α-star*'.
parse.skills_database_cache = ['Acceleration', 'Straightaway Acceleration',
                               'Corner Acceleration ○', 'Focus',
                               'Undivided Focus', 'α-star*', 'Speed Star']
for attr in ('cacheIndex', 'cacheSource', 'cacheTokenIndex', 'cacheNormMap'):
    if hasattr(parse.get_canonical_skill_name, attr):
        delattr(parse.get_canonical_skill_name, attr)
for ocr, want in (('Straightaway Acceleration', 'Straightaway Acceleration'),
                  ('Focus', 'Focus'),
                  ('Speed Star', 'Speed Star')):
    got = parse.get_canonical_skill_name(ocr)
    check(f"{ocr!r} resolves to itself, not a substring of it", got == want, got)
parse.skills_database_cache = None

print("\npruning to what the game actually has")
parse.reset_skills_database_cache()
with open(skills_db.USER_PATH, 'w', encoding='utf-8') as f:
    json.dump([{'name': 'Beast Mode'},            # in the fake database
               {'name': 'Corner Acceleration'},   # alias of a graded skill
               {'name': 'Invented Skill'}], f)    # in no database anywhere
big = os.path.join(tmp, 'big', 'master.mdb')
os.makedirs(os.path.dirname(big))
fake_mdb(big, ['Beast Mode', 'Corner Acceleration ○']
              + [f'Filler {i}' for i in range(skills_db.MIN_CREDIBLE_SKILLS)])
res5 = skills_db.prune(big)
kept = {s['name'] for s in json.load(open(skills_db.USER_PATH, encoding='utf-8'))}
check("a skill the game does not have is removed",
      'Invented Skill' not in kept, str(sorted(kept)))
check("  one it does have is kept", 'Beast Mode' in kept, str(sorted(kept)))
check("  and an un-suffixed alias of a graded skill survives",
      'Corner Acceleration' in kept, str(sorted(kept)))
check("  it reports what it removed", res5['removed'] == ['Invented Skill'],
      str(res5.get('removed')))

print("\nprune refuses rather than emptying the list")
small = os.path.join(tmp, 'small', 'master.mdb')
os.makedirs(os.path.dirname(small))
fake_mdb(small, ['Only One'])
before = json.load(open(skills_db.USER_PATH, encoding='utf-8'))
res6 = skills_db.prune(small)
after = json.load(open(skills_db.USER_PATH, encoding='utf-8'))
check("a database with implausibly few skills is refused", res6['ret'] == 1,
      str(res6))
check("  and nothing was written", before == after)
res7 = skills_db.prune(os.path.join(tmp, 'nowhere'))
check("a missing database prunes nothing", res7['ret'] == 1, str(res7))

print("\na missing database is reported, not raised")
res4 = skills_db.sync(os.path.join(tmp, 'definitely-not-here'))
check("it returns a failure", res4['ret'] == 1, str(res4))
check("  and names what it tried, so the message can say where to look",
      bool(res4.get('tried')), str(res4))

shutil.rmtree(tmp, ignore_errors=True)
print(f"\n{len(failures)} failed")
sys.exit(1 if failures else 0)
