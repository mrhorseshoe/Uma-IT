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

print("\nwhite requirement rows: every row, any entry within a row")
from uma_it.parse import spark_skill_rows_check, spark_rule_check
from uma_it.task import _skill_requirement_rows


def white(name, stars):
    return {'name': name, 'canonical': name, 'stars': stars,
            'color': 'white', 'y': 0}


HAVE = [white('URA Finale', 2), white('Corner Recovery ○', 1),
        white('Arima Kinen', 3)]

check("one row, one entry that is present",
      bool(spark_skill_rows_check(HAVE, [[{'name': 'URA Finale', 'stars': 2}]])))
check("  not present -> no match",
      spark_skill_rows_check(HAVE, [[{'name': 'Lay Low', 'stars': 1}]]) == '')
check("  present but short of the stars -> no match",
      spark_skill_rows_check(HAVE, [[{'name': 'URA Finale', 'stars': 3}]]) == '')
check("  more stars than asked for still matches",
      bool(spark_skill_rows_check(HAVE, [[{'name': 'Arima Kinen', 'stars': 1}]])))

# One entry per row is a pure AND; one row holding everything is a pure OR.
# Both fall out of the structure, which is the reason for choosing it.
AND_RULE = [[{'name': 'URA Finale', 'stars': 2}],
            [{'name': 'Arima Kinen', 'stars': 3}]]
check("a row each is a pure AND, and both are here",
      bool(spark_skill_rows_check(HAVE, AND_RULE)))
check("  and it fails when only one is",
      spark_skill_rows_check([white('URA Finale', 2)], AND_RULE) == '')

OR_RULE = [[{'name': 'Lay Low', 'stars': 1}, {'name': 'URA Finale', 'stars': 2}]]
check("one row is a pure OR, satisfied by the second entry",
      bool(spark_skill_rows_check(HAVE, OR_RULE)))
check("  and fails only when no entry is present",
      spark_skill_rows_check([white('Arima Kinen', 3)], OR_RULE) == '')

check("the grade symbol is not a difference",
      bool(spark_skill_rows_check(HAVE, [[{'name': 'Corner Recovery', 'stars': 1}]])),
      "stored target without ○ must match a row read with it")
check("no requirements is not a match on its own",
      spark_skill_rows_check(HAVE, []) == '')
check("a blue row cannot satisfy a white requirement",
      spark_skill_rows_check(
          [{'name': 'Speed', 'canonical': 'Speed', 'stars': 3,
            'color': 'blue', 'y': 0}],
          [[{'name': 'Speed', 'stars': 1}]]) == '')

print("\nthe whole rule: colour targets AND white rows")
BLUE = {'name': 'Speed', 'canonical': 'Speed', 'stars': 3, 'color': 'blue', 'y': 0}
rows = HAVE + [BLUE]
check("colour alone still works when no white rows are set",
      bool(spark_rule_check(rows, {'speed': 2}, 'or', 3, [])))
check("white alone works when no colour targets are set",
      bool(spark_rule_check(rows, {}, 'or', 3, [[{'name': 'URA Finale', 'stars': 2}]])))
check("  which is the parent-farming case, and it ignores the colours",
      bool(spark_rule_check([white('URA Finale', 2)], {}, 'or', 3,
                            [[{'name': 'URA Finale', 'stars': 2}]])))
check("both set means both must hold",
      bool(spark_rule_check(rows, {'speed': 2}, 'or', 3,
                            [[{'name': 'URA Finale', 'stars': 2}]])))
check("  colour hit but white missing -> no match",
      spark_rule_check(rows, {'speed': 2}, 'or', 3,
                       [[{'name': 'Lay Low', 'stars': 1}]]) == '')
check("  white hit but colour missing -> no match",
      spark_rule_check(rows, {'guts': 3}, 'or', 3,
                       [[{'name': 'URA Finale', 'stars': 2}]]) == '')
check("nothing targeted at all is never a match",
      spark_rule_check(rows, {}, 'or', 3, []) == '')

print("\nrequirement rows survive a payload")
check("a saved rule round-trips",
      _skill_requirement_rows([[{'name': 'URA Finale', 'stars': 2}]])
      == [[{'name': 'URA Finale', 'stars': 2}]])
check("  a bare name becomes a one-entry row at one star",
      _skill_requirement_rows(['URA Finale']) == [[{'name': 'URA Finale', 'stars': 1}]])
check("  stars are clamped to 1-3",
      _skill_requirement_rows([[{'name': 'X', 'stars': 9}]])[0][0]['stars'] == 3)
for junk in (None, 'nonsense', 42, [[]], [[{'name': ''}]], [{'nope': 1}]):
    check(f"  {junk!r} yields no requirement", _skill_requirement_rows(junk) == [],
          str(_skill_requirement_rows(junk)))

print("\nreading past the fold")
# 62% of captured frames hid at least one row, up to nine of eighteen. A
# targeted spark below the fold reads as absent, and that misreading is bought
# at 30 TP. These drive the scroll with a fake list so the merge, the
# termination and the refusal to guess are all exercised without the game.
import uma_it.parse as parse_mod
import uma_it.spark as spark_mod

spark_mod.time.sleep = lambda *_: None
parse_mod.time.sleep = lambda *_: None


class FakeList:
    """A spark list of `pages`, revealed a page at a time by swiping."""

    def __init__(self, pages, moves=True):
        self.pages, self.at, self.moves = pages, 0, moves
        self.swipes = 0

    def get_screen(self, to_gray=False):
        return ('screen', self.at)

    def swipe(self, **kw):
        self.swipes += 1
        if self.moves and self.at < len(self.pages) - 1:
            self.at += 1

    def click(self, *a, **k):
        pass


class ScrollCtx:
    def __init__(self, fake):
        self.ctrl = fake
        self.current_screen = None


def with_fake(fake, bottom_after_last=True):
    parse_mod.spark_list_at_bottom = (
        lambda img, tolerance=8: fake.at >= len(fake.pages) - 1)
    spark_mod.spark_list_at_bottom = parse_mod.spark_list_at_bottom
    parse_mod._parse_spark_rows_once = lambda ctx: fake.pages[fake.at]
    parse_mod.parse_spark_rows = lambda ctx, attempts=3: fake.pages[fake.at]


P1 = [white('Arima Kinen', 1), white('Lay Low', 1)]
P2 = [white('Lay Low', 1), white('URA Finale', 2)]          # overlaps P1
P3 = [white('URA Finale', 2), white('Fast-Paced', 3)]       # overlaps P2

fake = FakeList([P1, P2, P3])
with_fake(fake)
rows = parse_mod.read_all_spark_rows(ScrollCtx(fake))
names = [r['name'] for r in rows]
check("every page is read", len(rows) == 4, str(names))
check("  overlapping rows are merged, not duplicated",
      names.count('Lay Low') == 1 and names.count('URA Finale') == 1, str(names))

# The same row read on two overlapping pages comes back spelled differently.
# Live on 12 Sep: 'enno Sho (Autumn)' and 'ennoSho (Autumn)', 'edShift/LP1211-M'
# and 'ed Shift/LP1211-M'. Keyed on the raw OCR both survived and a ten-row
# list read as twelve, which would then lose the count-based tiebreak.
SAME_A = [{'name': 'enno Sho (Autumn)', 'canonical': 'Tenno Sho (Autumn)',
           'stars': 1, 'color': 'white', 'y': 0}]
SAME_B = [{'name': 'ennoSho (Autumn)', 'canonical': 'Tenno Sho (Autumn)',
           'stars': 1, 'color': 'white', 'y': 0}]
dup = FakeList([SAME_A, SAME_B])
with_fake(dup)
rows = parse_mod.read_all_spark_rows(ScrollCtx(dup))
check("  one row spelled two ways is still one row", len(rows) == 1,
      str([r['name'] for r in rows]))

# And with no canonical to lean on, letters-only still collapses a lost space.
UNRES_A = [{'name': 'edShift/LP1211-M', 'canonical': '', 'stars': 2,
            'color': 'green', 'y': 0}]
UNRES_B = [{'name': 'ed Shift/LP1211-M', 'canonical': '', 'stars': 2,
            'color': 'green', 'y': 0}]
dup2 = FakeList([UNRES_A, UNRES_B])
with_fake(dup2)
rows = parse_mod.read_all_spark_rows(ScrollCtx(dup2))
check("  and an unresolved row spelled two ways is one row", len(rows) == 1,
      str([r['name'] for r in rows]))
check("  and it stops at the bottom rather than swiping on",
      fake.swipes == 2, f"{fake.swipes} swipes")

# A list that will not move must not be swiped until the click guard trips.
stuck = FakeList([P1, P2], moves=False)
with_fake(stuck)
rows = parse_mod.read_all_spark_rows(ScrollCtx(stuck))
check("a list that does not move is given up on",
      stuck.swipes == 1, f"{stuck.swipes} swipes")

print("\nscrolling happens only when it could change the answer")
RULE = [[{'name': 'Fast-Paced', 'stars': 3}]]
SATISFIED = [[{'name': 'Arima Kinen', 'stars': 1}]]


class T:
    def __init__(self):
        self.detail = type('D', (), {})()


def decide(requirements, pages):
    f = FakeList(pages)
    with_fake(f)
    ctx = ScrollCtx(f)
    ctx.task = T()
    rows, hit = spark_mod._decide(ctx, pages[0], {}, 'or', 3, requirements)
    return f.swipes, hit


swipes, hit = decide(SATISFIED, [P1, P2, P3])
check("a rule the visible rows already satisfy does not scroll",
      swipes == 0 and hit, f"{swipes} swipes, hit {hit!r}")

swipes, hit = decide(RULE, [P1, P2, P3])
check("a rule that needs a hidden row scrolls and finds it",
      swipes > 0 and hit, f"{swipes} swipes, hit {hit!r}")

swipes, hit = decide([], [P1, P2, P3])
check("no white requirements never scrolls - blue and pink are always on top",
      swipes == 0, f"{swipes} swipes")

swipes, hit = decide([[{'name': 'Nothing Here', 'stars': 1}]], [P1, P2, P3])
check("a spark in no page still reports no match", hit == '', repr(hit))


# A scroll that throws must leave the decision on what was visible, and say so,
# rather than letting an exception read as "the spark is not there".
def boom(*a, **k):
    raise RuntimeError("adb fell over")


parse_mod.read_all_spark_rows = boom
spark_mod.read_all_spark_rows = boom
f = FakeList([P1, P2])
with_fake(f)
ctx = ScrollCtx(f)
ctx.task = T()
rows, hit = spark_mod._decide(ctx, P1, {}, 'or', 3, RULE)
check("a failed scroll falls back to the visible rows without raising",
      rows == P1 and hit == '', f"{len(rows)} rows, hit {hit!r}")

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
