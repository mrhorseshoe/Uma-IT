"""Spark reroll: the decisions, and the one that costs 30 TP to get wrong.

A reroll is the only thing in this app that spends a resource on purpose, so
the assertions here are about when it decides *not* to. The screen reading is
the parent's, moved verbatim; what is checked is what gets decided from it.

The blue/pink grouping gets its own section because the parent defines
SPARK_BLUE_NAMES twice - a capitalised list for name matching, then a lowercase
set for grouping, which shadows it. It works there by accident of ordering. Any
port that takes the wrong one classifies every blue spark as pink, silently,
and `mode: and` then never matches.
"""
import os, sys
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

import numpy as np

import uma_it.spark as spark
import uma_it.dialogs as dialogs
from uma_it.parse import spark_rows_check, SPARK_BLUE_KEYS, SPARK_BLUE_NAMES
from uma_it.asset.point import CULTIVATE_FACTOR_REROLL_SKIP, ESCAPE
from uma_it.context import CareerContext
from uma_it.task import build_task, EndTaskReason
from bot.base.task import TaskExecuteMode, TaskStatus

spark.time.sleep = lambda *_: None
dialogs.time.sleep = lambda *_: None

failures = []
NAME = lambda p: getattr(p, 'desc', p)


def check(label, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'}  {label}{'' if cond else '   ' + detail}")
    if not cond:
        failures.append(label)


def row(name, stars):
    return {'name': name, 'canonical': name, 'stars': stars,
            'color': 'blue' if name.lower() in SPARK_BLUE_KEYS else 'pink', 'y': 0}


class FakeCtrl:
    def __init__(self):
        self.clicks = []

    def get_screen(self, to_gray=False):
        return np.zeros((1280, 720, 3), np.uint8)

    def click_by_point(self, point):
        self.clicks.append(NAME(point))

    def click(self, x, y, name):
        self.clicks.append((x, y, name))


class FakeCtx:
    def __init__(self, career_state=None, **settings):
        self.ctrl = FakeCtrl()
        self.career = CareerContext()
        for k, v in (career_state or {}).items():
            setattr(self.career, k, v)
        self.current_screen = np.zeros((1280, 720, 3), np.uint8)
        self.task = build_task(TaskExecuteMode.TASK_EXECUTE_MODE_LOOP, 1,
                               "check", None, settings)
        self.ended = []
        self.task.end_task = lambda s, r: self.ended.append((s, r))


print("the two constants that must not be the same thing")
check("the matching list is capitalised", "Speed" in SPARK_BLUE_NAMES, str(SPARK_BLUE_NAMES))
check("the grouping set is lowercase", "speed" in SPARK_BLUE_KEYS, str(SPARK_BLUE_KEYS))

print("\ngrouping and thresholds")
check("a blue target is matched by a blue spark",
      spark_rows_check([row('Speed', 3)], {'speed': 3}) == 'Speed')
check("a pink target is matched by a pink spark",
      spark_rows_check([row('Turf', 3)], {'turf': 3}) == 'Turf')
check("stars below the target do not match",
      spark_rows_check([row('Speed', 2)], {'speed': 3}) == '',
      spark_rows_check([row('Speed', 2)], {'speed': 3}))
check("stars above the target do match",
      spark_rows_check([row('Speed', 3)], {'speed': 2}) == 'Speed')
check("each target carries its own minimum",
      spark_rows_check([row('Speed', 1), row('Turf', 3)],
                       {'speed': 3, 'turf': 3}) == 'Turf')
check("no targets means never reroll", spark_rows_check([row('Speed', 3)], {}) == '')

print("\n  'and' needs one from each group - the case the shadowed name broke")
both = [row('Speed', 3), row('Turf', 3)]
check("'and' matches when both groups hit",
      spark_rows_check(both, {'speed': 3, 'turf': 3}, 'and') == 'Speed + Turf',
      spark_rows_check(both, {'speed': 3, 'turf': 3}, 'and'))
check("'and' does not match on blue alone",
      spark_rows_check([row('Speed', 3)], {'speed': 3, 'turf': 3}, 'and') == '')
check("'and' does not match on pink alone",
      spark_rows_check([row('Turf', 3)], {'speed': 3, 'turf': 3}, 'and') == '')
check("'or' matches on either",
      spark_rows_check([row('Turf', 3)], {'speed': 3, 'turf': 3}, 'or') == 'Turf')
check("a legacy flat list of targets still works",
      spark_rows_check([row('Speed', 3)], ['speed'], 'or', 3) == 'Speed')

print("\nrerolling is off unless asked for")
ctx = FakeCtx()
check("no targets and not enabled means inactive", spark._spark_reroll_active(ctx) is False)
ctx = FakeCtx(spark_reroll_enabled=True)
check("enabled with no targets is still inactive", spark._spark_reroll_active(ctx) is False)
ctx = FakeCtx(spark_reroll_enabled=True, spark_reroll_targets={'speed': 3})
check("enabled with a target is active", spark._spark_reroll_active(ctx) is True)

print("\na satisfied first roll is kept, not rerolled")
spark.parse_spark_rows = lambda _ctx: [row('Speed', 3)]
ctx = FakeCtx(career_state={'parse_factor_done': True},
              spark_reroll_enabled=True, spark_reroll_targets={'speed': 3})
spark.script_factor_reroll(ctx)
check("it confirms without rerolling",
      ctx.ctrl.clicks == [NAME(CULTIVATE_FACTOR_REROLL_SKIP)], str(ctx.ctrl.clicks))
check("  and records why", ctx.career.spark_reroll_result.get('rerolled') is False,
      str(ctx.career.spark_reroll_result))
check("  and counts it as a run that met the requirements",
      ctx.task.detail.spark_goal_runs == 1, str(ctx.task.detail.spark_goal_runs))

print("\nan unreadable roll is kept rather than gambled on")
spark.parse_spark_rows = lambda _ctx: []
ctx = FakeCtx(career_state={'parse_factor_done': True},
              spark_reroll_enabled=True, spark_reroll_targets={'speed': 3})
spark.script_factor_reroll(ctx)
check("no parsed rows means confirm, not reroll",
      ctx.ctrl.clicks == [NAME(CULTIVATE_FACTOR_REROLL_SKIP)], str(ctx.ctrl.clicks))

print("\nrunning out of TP mid-reroll must not fail the career")
# The career is already over by this point; the reroll is the only thing lost.
# Before this interception existed, 'Confirm' would reach the TP handler and
# end the run as failed.
spark.ocr_line = lambda _img: "You need 12 more TP to reroll Sparks. Restore TP?"
spark.find_green_button = lambda *_a: (500, 900)
ctx = FakeCtx(career_state={'spark_reroll_phase': 'reroll_clicked'},
              spark_reroll_enabled=True, spark_reroll_targets={'speed': 3})
handled = spark.intercept_dialog(ctx, ((0, 0), (0, 400)))
check("the dialog is claimed by the reroll flow", handled is True)
check("  the career is not ended", ctx.ended == [], str(ctx.ended))
check("  the phase moves to abort", ctx.career.spark_reroll_phase == 'abort',
      ctx.career.spark_reroll_phase)
check("  and it declines rather than confirming",
      ctx.ctrl.clicks == [(220, 900, "Decline TP restore (keep the first roll)")],
      str(ctx.ctrl.clicks))

print("\n  and the router sends it there rather than to the TP handler")
dialogs.read_title = lambda _ctx: 'Confirm'
ctx = FakeCtx(career_state={'spark_reroll_phase': 'reroll_clicked'},
              allow_recover_tp=0, spark_reroll_enabled=True,
              spark_reroll_targets={'speed': 3})
dialogs.script_dialog(ctx)
check("'Confirm' during a reroll does not fail the career", ctx.ended == [],
      str(ctx.ended))

# ...but with no reroll in flight it still must.
ctx = FakeCtx(allow_recover_tp=0)
dialogs.script_dialog(ctx)
check("'Confirm' outside a reroll still fails the career",
      [r for _, r in ctx.ended] == [EndTaskReason.TP_NOT_ENOUGH], str(ctx.ended))

print("\nan aborted reroll keeps the original sparks")
ctx = FakeCtx(career_state={'parse_factor_done': True, 'spark_reroll_phase': 'abort'},
              spark_reroll_enabled=True, spark_reroll_targets={'speed': 3})
spark.script_factor_reroll(ctx)
check("it confirms the original set",
      ctx.ctrl.clicks == [NAME(CULTIVATE_FACTOR_REROLL_SKIP)], str(ctx.ctrl.clicks))
check("  and says so in the result",
      ctx.career.career_result.get('spark_reroll', {}).get('chosen') == 'original',
      str(ctx.career.career_result))

# When neither set has a wanted spark the rule is "keep the set with the most
# sparks". The scrollbar thumb answers that whenever a list overflows its page.
# When neither does, both thumbs read the no-scrollbar sentinel 1.0, and the
# comparison used to fall through to total stars - a different question, which
# a three-row set with high stars wins over an eight-row one.
print("\nneither set qualifies: the bigger set wins")


def choose(rerolled, original, ratio_rerolled, ratio_original, roll1=None,
           targets=None):
    """Drive handle_spark_selection over a scripted carousel.

    `roll1` is roll 1 as the reroll screen read it, past the fold if need be.
    """
    state = {'view': 'rerolled'}
    rows = {'rerolled': rerolled, 'original': original}
    ratios = {'rerolled': ratio_rerolled, 'original': ratio_original}

    def show(ctx, want):
        state['view'] = want
        return True

    spark._spark_selection_show_view = show
    spark._spark_selection_confirm = lambda ctx: True
    spark._save_spark_debug = lambda *a, **k: None
    spark.parse_spark_rows = lambda ctx, **kw: rows[state['view']]
    spark.spark_scrollbar_ratio = lambda img: ratios[state['view']]

    ctx = FakeCtx(career_state={'spark_reroll_phase': 'reroll_clicked',
                                'spark_roll1_rows': roll1 or []},
                  spark_reroll_enabled=True,
                  spark_reroll_targets=targets or {'nothing-matches-this': 3})
    spark.handle_spark_selection(ctx)
    return dict(ctx.career.spark_reroll_result,
                goal_runs=ctx.task.detail.spark_goal_runs)


big = [row('speed', 1), row('mile', 1)] + [row(f'race{i}', 1) for i in range(6)]
small_but_starry = [row('stamina', 3), row('dirt', 3), row('race9', 3)]

res = choose(big, small_but_starry, 1.0, 1.0)
check("8 rows beats 3 rows when both lists fit one page",
      res['chosen'] == 'rerolled', f"{res['chosen']} - {res['reason']}")
check("  and it says it counted sparks, not stars",
      'rows' in res['reason'] and 'star' not in res['reason'], res['reason'])

res = choose(small_but_starry, big, 1.0, 1.0)
check("  and the same the other way round", res['chosen'] == 'original',
      f"{res['chosen']} - {res['reason']}")

# A genuine tie still falls through to stars, which is what it is for.
res = choose([row('speed', 1), row('mile', 1)], [row('stamina', 3), row('dirt', 3)],
             1.0, 1.0)
check("equal row counts still fall through to total stars",
      res['chosen'] == 'original' and 'star' in res['reason'], res['reason'])

# And a measurable scrollbar still decides, since it sees below the fold.
# Measured on the captured frames a scrollbar appears only at 9 rows, so the
# row counts here are equal and only the thumb can separate them.
nine = [row(f'r{i}', 1) for i in range(9)]
res = choose(nine, list(nine), 0.70, 0.90)
check("a shorter thumb still wins when the lists overflow",
      res['chosen'] == 'rerolled' and 'scrollbar' in res['reason'], res['reason'])
res = choose(nine, list(nine), 1.0, 0.70)
check("  and a full page loses to one with rows below the fold",
      res['chosen'] == 'original', f"{res['chosen']} - {res['reason']}")

# Career 2, 14 Sep: both sets 13 sparks, so the thumbs tied and it came down to
# stars - but the rerolled set had been read past the fold and the original
# only to it, 21 stars against 9 rows' 13. Here the fair count (18 vs 16)
# favours the original and the unfair one (16 vs 10) the rerolled set.
full_rerolled = [row(f'n{i}', 1) for i in range(10)] + [row('x', 2), row('y', 2), row('z', 2)]
original_full = [row(f'o{i}', 1) for i in range(8)] + [row(f'p{i}', 2) for i in range(5)]
original_visible = original_full[:9]
res = choose(full_rerolled, original_visible, 0.66, 0.66, roll1=original_full)
check("a star tie-break counts the original set in full, as it counts the rerolled one",
      res['chosen'] == 'original' and '16 vs 18' in res['reason'],
      f"{res['chosen']} - {res['reason']}")
check("  and records the full original set",
      len(res['original']) == 13, str(len(res['original'])))

print("\ncounting runs whose kept sparks met every requirement")
res = choose(big, small_but_starry, 1.0, 1.0)
check("a run where neither set qualifies is not counted", res['goal_runs'] == 0,
      str(res['goal_runs']))
res = choose([row('Speed', 3)], small_but_starry, 1.0, 1.0, targets={'speed': 3})
check("a rerolled set that qualifies is counted, once",
      res['chosen'] == 'rerolled' and res['goal_runs'] == 1,
      f"{res['chosen']} {res['goal_runs']}")

print(f"\n{len(failures)} failed")
sys.exit(1 if failures else 0)
