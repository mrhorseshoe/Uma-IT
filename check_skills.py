"""Skill buying: what gets bought, and what must not get edited.

Two kinds of assertion here.

The **choice** - priority order first, then spending whatever is left. Points
not spent at the end of a career are lost, so the assertions here are mostly
about not stopping early: an unaffordable skill must not end its tier, and an
unaffordable tier must not end the search.

The **copy** - the buying pass removes skills from the priority list as it
learns them. In this project that list is a task setting, and task settings are
serialized to disk, so editing the wrong one deletes skills from the saved
preset permanently. That is the assertion worth having here.
"""
import os, sys
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

import numpy as np

import uma_it.skills as skills_mod
from uma_it.asset.point import RETURN_TO_CULTIVATE_FINISH, CULTIVATE_LEARN_SKILL_CONFIRM
from uma_it.const import SKILL_LEARN_PRIORITY_LIST
from uma_it.context import CareerContext
from uma_it.parse import load_skills_database, get_canonical_skill_name
from uma_it.task import build_task
from bot.base.task import TaskExecuteMode

skills_mod.time.sleep = lambda *_: None
failures = []
NAME = lambda p: getattr(p, 'desc', p)


def check(label, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'}  {label}{'' if cond else '   ' + detail}")
    if not cond:
        failures.append(label)


def skill(name, cost, priority, hint=0, gold=False, available=True):
    return {'skill_name': name, 'skill_name_raw': name, 'skill_cost': cost,
            'priority': priority, 'hint_level': hint, 'gold': gold,
            'available': available, 'subsequent_skill': ''}


class FakeCtrl:
    def __init__(self):
        self.clicks, self.swipes = [], []

    def get_screen(self, to_gray=False):
        return np.zeros((1280, 720, 3), np.uint8)

    def click_by_point(self, point):
        self.clicks.append(NAME(point))

    def click(self, x, y, name):
        self.clicks.append((x, y, name))

    def swipe(self, **kw):
        self.swipes.append(kw.get('name', 'swipe'))


class FakeCtx:
    def __init__(self, career_state=None, **settings):
        self.ctrl = FakeCtrl()
        self.career = CareerContext()
        for k, v in (career_state or {}).items():
            setattr(self.career, k, v)
        self.current_screen = np.zeros((1280, 720, 3), np.uint8)
        self.task = build_task(TaskExecuteMode.TASK_EXECUTE_MODE_LOOP, 1,
                               "check", None, settings)
        self.task.running = lambda: True


print("the skills database ships with the project")
db = load_skills_database()
# The floor used to be 1,000, sized to a 1,536-entry wiki scrape. The shipped
# list is now pruned to what the game's own database has - 521 entries covering
# all 520 of its distinct skills - so the old floor measured the scrape rather
# than the thing it was guarding, which is "the file loaded and is not
# truncated". Sized to the game instead, with room for it to grow.
check("it loads", len(db) > 400, f"{len(db)} names")
check("OCR of a symbol-suffixed name canonicalises",
      get_canonical_skill_name("Corner Acceleration O") == "Corner Acceleration",
      get_canonical_skill_name("Corner Acceleration O"))

print("\nchoosing what to buy")
tiers = [['a'], ['b']]
chosen, _, spent, _ = skills_mod._choose(
    [skill('a', 100, 0), skill('b', 100, 1)], tiers, 300)
check("buys across tiers when it can afford both", chosen == ['a', 'b'], str(chosen))
check("  and adds up the cost", spent == 200, str(spent))

# Points not spent at the end of a career are lost, so an unaffordable skill
# must never stop the search. The parent breaks on both counts, and measured
# against the built-in list a 300-point budget facing a 400-point skill bought
# nothing at all - twice over, with affordable skills right there.
chosen, _, spent, _ = skills_mod._choose([skill('a', 400, 0), skill('b', 100, 1)], tiers, 300)
check("an unaffordable top tier does not stop the lower ones",
      chosen == ['b'] and spent == 100, f"{chosen} {spent}")

chosen, _, spent, _ = skills_mod._choose(
    [skill('dear', 400, 0, hint=3), skill('cheap', 50, 0)], [['dear', 'cheap']], 300)
check("an unaffordable skill does not stop the rest of its own tier",
      chosen == ['cheap'] and spent == 50, f"{chosen} {spent}")

# The filler must only ever take budget the good skills declined.
chosen, _, _, _ = skills_mod._choose(
    [skill('low', 100, 2), skill('top', 100, 0)], [['top'], [], ['low']], 500)
check("priority order still decides who buys first", chosen == ['top', 'low'],
      str(chosen))

# Whatever is left must be smaller than the cheapest thing still on offer -
# that is what "no points left on the table" means, checkably.
pool = [skill('A', 180, 0, hint=3), skill('B', 160, 0, hint=1), skill('C', 120, 1),
        skill('D', 90, 1), skill('E', 70, 2), skill('F', 45, 3), skill('G', 30, 3)]
chosen, _, spent, _ = skills_mod._choose(pool, [['A', 'B'], ['C', 'D'], ['E']], 500)
unbought = [x['skill_cost'] for x in pool if x['skill_name'] not in chosen]
check("nothing affordable is left unbought",
      not unbought or (500 - spent) < min(unbought),
      f"{500 - spent} left, cheapest unbought {min(unbought) if unbought else None}")

# learn_skill_only_user_provided has to actually restrict. get_skill_list files
# unnamed skills one tier past the end, and without this they were bought too.
listed = [skill('named', 100, 0), skill('unnamed', 50, 1)]
chosen, _, _, _ = skills_mod._choose(listed, [['named']], 500, only_listed=True)
check("only-what-I-list leaves the unlisted bucket alone", chosen == ['named'],
      str(chosen))
for x in listed:
    x['available'] = True
chosen, _, _, _ = skills_mod._choose(listed, [['named']], 500, only_listed=False)
check("  and without it the leftovers are spent on unlisted skills",
      chosen == ['named', 'unnamed'], str(chosen))

chosen, _, _, _ = skills_mod._choose(
    [skill('x', 100, 0, hint=0), skill('y', 100, 0, hint=3)], [['x', 'y']], 100)
check("prefers the higher hint level within a tier", chosen == ['y'], str(chosen))

chosen, _, _, _ = skills_mod._choose(
    [skill('a', 100, 0, available=False), skill('b', 100, 0)], [['a', 'b']], 500)
check("never buys an already-learned skill", chosen == ['b'], str(chosen))

pool = [skill('gold', 100, 0, gold=True), skill('lesser', 100, 0)]
pool[0]['subsequent_skill'] = 'lesser'
chosen, _, _, _ = skills_mod._choose(pool, [['gold', 'lesser']], 500)
check("a gold skill supersedes the one bound below it", chosen == ['gold'], str(chosen))

# The owner's order, 14 Sep: priority skills, then the ◎ of priority skills
# already bought at ○ (a higher grade sparks more often), then anything else.
# A ◎ is only offered once its ○ is learned, so the pass that buys a priority
# ○ has to hold points back.
print("\nthree stages: priority, their ◎ upgrades, everything else")
cb = skills_mod.circle_base
check("a trailing O is read as a grade symbol",
      (cb('Cloudy Days O'), cb('Right-HandedO'), cb('Muddy ◎'))
      == ('cloudydays', 'righthanded', 'muddy'),
      str((cb('Cloudy Days O'), cb('Right-HandedO'), cb('Muddy ◎'))))
check("  and a plain name is not a circle skill", cb('Groundwork') is None)

three = lambda: [skill('Groundwork', 100, 0), skill('Cloudy Days O', 60, 0),
                 skill('Pressure', 50, 1)]
PRIORITY = [['Groundwork', 'Cloudy Days O']]
chosen, _, _, held = skills_mod._choose(three(), PRIORITY, 1000)
check("a priority ○ holds back a ◎'s worth for the next pass", held == 75, str(held))
chosen, _, _, _ = skills_mod._choose(three(), PRIORITY, 234)
check("other skills cannot spend what is held for that ◎",
      chosen == ['Groundwork', 'Cloudy Days O'], str(chosen))
chosen, _, _, _ = skills_mod._choose(three(), PRIORITY, 285)
check("  but take it once the hold is covered",
      chosen == ['Groundwork', 'Cloudy Days O', 'Pressure'], str(chosen))

chosen, _, _, held = skills_mod._choose(
    [skill('Cloudy Days O', 60, 0), skill('Pressure', 50, 0)], [], 1000)
check("an unlisted ○ is an ordinary skill: no hold, no place ahead",
      chosen == ['Pressure', 'Cloudy Days O'] and held == 0, f"{chosen} {held}")

chosen, _, _, held = skills_mod._choose(
    [skill('Pressure', 50, 0), skill('Cloudy Days O', 60, 0)], [], 60,
    circles_owned={'cloudydays'})
check("a later pass buys the ◎ of a priority ○ before anything else",
      chosen == ['Cloudy Days O'] and held == 0, f"{chosen} {held}")
# Career 4, 14 Sep: both ◎ rows OCR'd with no symbol at all.
chosen, _, _, _ = skills_mod._choose(
    [skill('Pressure', 50, 0), skill('Wet Conditions ', 66, 0)], [], 66,
    circles_owned={'wetconditions'})
check("  even when OCR drops the ◎ entirely", chosen == ['Wet Conditions '], str(chosen))

chosen, _, _, _ = skills_mod._choose(
    [skill('dear', 300, 0, hint=3), skill('x', 100, 0), skill('y', 100, 0),
     skill('z', 100, 0)], [], 300)
check("everything else goes cheapest first, for the most skills",
      sorted(chosen) == ['x', 'y', 'z'], str(chosen))
chosen, _, _, held = skills_mod._choose(
    [skill('named', 100, 0), skill('Cloudy Days O', 50, 1)], [['named']], 500,
    only_listed=True)
check("only-what-I-list skips the circle stage as well",
      chosen == ['named'] and held == 0, f"{chosen} {held}")

print("\nthe point total is read once the screen settles")
reads = iter([0, 3734, 3734])
skills_mod._read_skill_points = lambda _ctx: next(reads)
got = skills_mod._settled_skill_points(FakeCtx())
check("an early 0 is not believed", got == 3734, str(got))
reads = iter([0] * 6)
skills_mod._read_skill_points = lambda _ctx: next(reads)
got = skills_mod._settled_skill_points(FakeCtx())
check("  but a total that stays 0 is", got == 0, str(got))

print("\nOCR that drops a space still names the skill")
for text, want in (('After-SchoolStroll', 'After-School Stroll'),
                   ('UmaStan', 'Uma Stan'), ('SpringRunner O', 'Spring Runner')):
    got = get_canonical_skill_name(text)
    check(f"{text!r} -> {want!r}", got == want, repr(got))

print("\nthe task's saved preset is never edited")
saved = [['Corner Acceleration'], ['Focus']]
ctx = FakeCtx(learn_skill_list=saved, skip_learn_skill=False)
before = [list(t) for t in ctx.task.detail.learn_skill_list]
skills_mod.get_skill_list = lambda _img, _w, _b: [skill('Corner Acceleration', 50, 0)]
skills_mod.find_skill = lambda _ctx, _img, to_click, **kw: (to_click.clear() or True)
skills_mod._read_skill_points = lambda _ctx: 500
skills_mod.compare_color_equal = lambda *_a: False
skills_mod.script_learn_skill(ctx)
check("the skill is bought", ctx.career.learn_skill_done is True)
check("  and the task's list is untouched",
      ctx.task.detail.learn_skill_list == before, str(ctx.task.detail.learn_skill_list))
check("  while the run's copy has it removed",
      all('Corner Acceleration' not in tier for tier in ctx.career.remaining_skills),
      str(ctx.career.remaining_skills))
check("  and it confirms at the end",
      ctx.ctrl.clicks[-1] == NAME(CULTIVATE_LEARN_SKILL_CONFIRM), str(ctx.ctrl.clicks))

print("\na pass remembers only what it actually clicked")
cloudy = lambda _img, _w, _b: [dict(skill('Cloudy Days O', 60, 0),
                                    skill_name_raw='Cloudy Days')]
skills_mod.get_skill_list = cloudy
ctx = FakeCtx(learn_skill_list=[['Cloudy Days']], skip_learn_skill=False)
skills_mod.script_learn_skill(ctx)
check("a clicked ○ is recorded, so the next pass knows its ◎",
      ctx.career.circle_skills == {'cloudydays'}, str(ctx.career.circle_skills))
check("  and it leaves the run's list", ctx.career.remaining_skills == [],
      str(ctx.career.remaining_skills))

skills_mod.get_skill_list = lambda _img, _w, _b: [dict(skill('Cloudy Days O', 60, 1),
                                                       skill_name_raw='')]
ctx = FakeCtx(learn_skill_list=[['Groundwork']], skip_learn_skill=False)
skills_mod.script_learn_skill(ctx)
check("an unlisted ○ that gets bought is not lined up for a ◎",
      not ctx.career.circle_skills, str(ctx.career.circle_skills))
skills_mod.get_skill_list = cloudy

sweeps = []
skills_mod.find_skill = lambda _ctx, _img, to_click, **kw: (sweeps.append(1), False)[1]
ctx = FakeCtx(learn_skill_list=[['Cloudy Days']], skip_learn_skill=False)
skills_mod.script_learn_skill(ctx)
check("a chosen skill not found gets a second sweep", len(sweeps) == 2, str(len(sweeps)))
check("  and, never clicked, keeps its priority tier",
      ctx.career.remaining_skills == [['Cloudy Days']], str(ctx.career.remaining_skills))
check("  and is not recorded as owned", not ctx.career.circle_skills,
      str(ctx.career.circle_skills))
skills_mod.find_skill = lambda _ctx, _img, to_click, **kw: (to_click.clear() or True)

seen = {}
ctx = FakeCtx(learn_skill_list=[['Cloudy Days']], skip_learn_skill=False)
ctx.career.remaining_skills = []
skills_mod.get_skill_list = lambda _img, wanted, _b: (seen.__setitem__('wanted', wanted), [])[1]
skills_mod.script_learn_skill(ctx)
check("once the task's own list is bought, the shipped tiers do not take over",
      seen.get('wanted') == [], str(seen.get('wanted')))

# The click that actually spends the points, and the screen it belongs to.
# CONFIRMATION_LEARNSKILL_BUTTON is a crop of this dialog's Learn button, so it
# matches the dialog and nothing else - but the manifest called the two "both
# crops of the same screen" and pointed both at script_learn_skill. Arriving
# there with the pass done takes the _leave branch and clicks Back at
# (90, 1190), which is inside this dialog, on Cancel. Four passes over the same
# 4108 points on 11 Sep, every one discarded.
print("\nthe 'Learn the above skills?' dialog is its own screen")
from uma_it.asset.ui import CONFIRMATION_LEARNSKILL_BUTTON, CULTIVATE_LEARN_SKILL
from uma_it.asset.point import CULTIVATE_LEARN_SKILL_CONFIRM_AGAIN
from uma_it.manifest import script_dicts
from uma_it.task import UmaItTaskType

table = script_dicts[UmaItTaskType.CAREER]
check("it has a handler of its own",
      table.get(CONFIRMATION_LEARNSKILL_BUTTON) is not table.get(CULTIVATE_LEARN_SKILL),
      str(table.get(CONFIRMATION_LEARNSKILL_BUTTON)))

ctx = FakeCtx(career_state={'learn_skill_done': True}, skip_learn_skill=False)
table[CONFIRMATION_LEARNSKILL_BUTTON](ctx)
check("  and it clicks Learn",
      ctx.ctrl.clicks == [NAME(CULTIVATE_LEARN_SKILL_CONFIRM_AGAIN)],
      str(ctx.ctrl.clicks))
check("  never Back, which lands on this dialog's Cancel",
      NAME(RETURN_TO_CULTIVATE_FINISH) not in ctx.ctrl.clicks, str(ctx.ctrl.clicks))

# Back is (90, 1190) and this dialog's Cancel spans roughly x 63-341,
# y 1148-1218 - measured off the frame the bot was looping on. Anything routed
# to this screen that clicks Back is pressing Cancel, whatever it meant to do.
bx, by = (RETURN_TO_CULTIVATE_FINISH.coordinate.x,
          RETURN_TO_CULTIVATE_FINISH.coordinate.y)
check("  (the Back point really is on Cancel)",
      63 <= bx <= 341 and 1148 <= by <= 1218, f"({bx}, {by})")

print("\nleaving without buying")
ctx = FakeCtx(career_state={'learn_skill_done': True}, skip_learn_skill=False)
skills_mod.script_learn_skill(ctx)
check("a second visit just returns",
      ctx.ctrl.clicks == [NAME(RETURN_TO_CULTIVATE_FINISH)], str(ctx.ctrl.clicks))

ctx = FakeCtx(learn_skill_list=[], learn_skill_only_user_provided=True,
              skip_learn_skill=False)
skills_mod.script_learn_skill(ctx)
check("an empty user list with only-user-provided returns without buying",
      ctx.ctrl.clicks == [NAME(RETURN_TO_CULTIVATE_FINISH)], str(ctx.ctrl.clicks))

ctx = FakeCtx(skip_learn_skill=False)
skills_mod.get_skill_list = lambda _img, _w, _b: [skill('a', 9999, 0)]
skills_mod._read_skill_points = lambda _ctx: 10
skills_mod.script_learn_skill(ctx)
check("nothing affordable returns rather than stalling",
      ctx.ctrl.clicks[-1] == NAME(RETURN_TO_CULTIVATE_FINISH), str(ctx.ctrl.clicks))

print("\nthe default priority list is used when the task names none")
seen = {}
ctx = FakeCtx(skip_learn_skill=False)
skills_mod.get_skill_list = lambda _img, wanted, _b: seen.setdefault('wanted', wanted) and []
skills_mod.get_skill_list = lambda _img, wanted, _b: (seen.__setitem__('wanted', wanted), [])[1]
skills_mod.script_learn_skill(ctx)
check("it falls back to the shipped tiers",
      seen.get('wanted') is SKILL_LEARN_PRIORITY_LIST, str(type(seen.get('wanted'))))

print(f"\n{len(failures)} failed")
sys.exit(1 if failures else 0)
