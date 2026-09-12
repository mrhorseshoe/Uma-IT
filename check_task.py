"""A task must survive being written to disk and read back.

This is the check for the failure that has already cost this project's parent a
task definition. The mechanism, in order: a setting fails to serialize, the
entry persists with a null or short payload, rebuilding it raises, the loader
catches that with `except Exception: continue` and drops the task, and the next
save writes the shortened list back. Nothing in that chain logs an error, and
the bot soft-restarts after every career, so the first restart is enough.

So: build a task, serialize it with the engine's real serializer, rebuild it,
and compare. Plus the two payload shapes that must not raise - an empty one,
and one from the parent project carrying fifty keys this app does not know.
"""
import os, sys
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

from bot.base.purge import serialize_umamusume_task
from bot.base.task import TaskExecuteMode, TaskStatus, EndTaskReason
from uma_it.task import EndTaskReason as UmaItEndReason
from uma_it.task import build_task, APP_NAME
from uma_it.define import ScenarioType

LOOP = TaskExecuteMode.TASK_EXECUTE_MODE_LOOP
failures = []


def check(label, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'}  {label}{'' if cond else '   ' + detail}")
    if not cond:
        failures.append(label)


# The payload actually in use when this project started: the owner's single
# saved task, an unlimited Independent Training loop with skills skipped and
# TP recovery refused.
REAL = {
    "scenario": 4,
    "follow_support_card_name": "Wave of Gratitude",
    "use_last_parents": True,
    "loop_count": 0,
    "loops_done": 26,
    "allow_recover_tp": 0,
    "skip_learn_skill": True,
    "learn_skill_list": [[]],
    "learn_skill_blacklist": [],
    "learn_skill_only_user_provided": False,
    "learn_skill_threshold": 888,
    "manual_purchase_at_end": False,
    "spark_reroll_enabled": False,
    "spark_reroll_targets": {},
    "spark_reroll_mode": "or",
    "spark_reroll_min_stars": 3,
    "spark_reroll_use_carats": False,
    "stop_at_spark_reroll": False,
}

SETTINGS = sorted(k for k in REAL)

print("round trip: build -> serialize -> build")
t1 = build_task(LOOP, 1, "Training", None, REAL)
blob = serialize_umamusume_task(t1)
check("serializer returned a payload", isinstance(blob, dict) and bool(blob),
      f"got {type(blob).__name__}")
t2 = build_task(LOOP, 1, "Training", None, blob or {})

for k in SETTINGS:
    a, b = getattr(t1.detail, k, None), getattr(t2.detail, k, None)
    check(f"{k} survives", a == b, f"{a!r} != {b!r}")

check("app_name is uma-it", t1.app_name == APP_NAME, t1.app_name)
check("scenario stays an enum", isinstance(t2.detail.scenario, ScenarioType),
      type(t2.detail.scenario).__name__)
check("loops_done kept its count", t2.detail.loops_done == 26,
      str(t2.detail.loops_done))

print("\npayloads that must not raise")
try:
    empty = build_task(LOOP, 1, "empty", None, {})
    check("an empty payload builds", True)
    check("  and defaults to refusing TP spend", empty.detail.allow_recover_tp == 0)
    check("  and defaults to unlimited loops", empty.detail.loop_count == 0)
except Exception as e:
    check("an empty payload builds", False, f"{type(e).__name__}: {e}")

try:
    build_task(LOOP, 1, "none", None, None)
    check("a null payload builds", True)
except Exception as e:
    check("a null payload builds", False, f"{type(e).__name__}: {e}")

# The parent project's payload: every key this app dropped, plus the ones it
# kept. Unknown keys must be ignored, not fatal.
PARENT = dict(REAL)
PARENT.update({
    "expect_attribute": [9999] * 5, "tactic_list": [4, 4, 4], "clock_use_limit": 99,
    "extra_weight": [[0] * 5] * 4, "spirit_explosion": [0.16] * 5,
    "compensate_failure": True, "cure_asap_conditions": "", "rest_treshold": 48,
    "motivation_threshold_year1": 3, "pal_name": "", "pal_thresholds": [],
    "ura_config": None, "aoharu_config": None, "fujikiseki_show_mode": False,
    "fujikiseki_show_difficulty": 0, "do_tt_next": False, "extra_race_list": [],
    "independent_training": True, "learn_skill_only_at_end": False,
    "override_insufficient_fans_forced_races": False, "event_weights": None,
})
try:
    p = build_task(LOOP, 1, "parent", None, PARENT)
    check("a parent-project payload builds", True)
    check("  and keeps the settings it shares",
          p.detail.follow_support_card_name == "Wave of Gratitude"
          and p.detail.loops_done == 26)
except Exception as e:
    check("a parent-project payload builds", False, f"{type(e).__name__}: {e}")

print("\nthe loop counter")
t3 = build_task(LOOP, 1, "counting", None, REAL)
t3.end_task(TaskStatus.TASK_STATUS_SUCCESS, EndTaskReason.COMPLETE)
check("a finished run increments loops_done", t3.detail.loops_done == 27,
      str(t3.detail.loops_done))
after = build_task(LOOP, 1, "counting", None, serialize_umamusume_task(t3) or {})
check("  and the increment survives a round trip", after.detail.loops_done == 27,
      str(after.detail.loops_done))

# A failed career is not a career the user asked for. Counting one as a run
# made "2 of 2 runs" true of a two-run loop that reported itself finished in
# thirty seconds on 11 Sep, both careers having died on the TP prompt before
# either began.
t4 = build_task(LOOP, 2, "counting", None, dict(REAL, loops_done=0, loop_count=2))
t4.end_task(TaskStatus.TASK_STATUS_FAILED, UmaItEndReason.TP_NOT_ENOUGH)
check("a failed career does not consume a run", t4.detail.loops_done == 0,
      str(t4.detail.loops_done))
check("  but is counted as a failure", t4.detail.consecutive_failures == 1,
      str(t4.detail.consecutive_failures))
back = build_task(LOOP, 2, "counting", None, serialize_umamusume_task(t4) or {})
check("  and the failure count survives a round trip",
      back.detail.consecutive_failures == 1, str(back.detail.consecutive_failures))

t4.end_task(TaskStatus.TASK_STATUS_SUCCESS, EndTaskReason.COMPLETE)
check("a career that completes clears the failure streak",
      t4.detail.consecutive_failures == 0 and t4.detail.loops_done == 1,
      f"{t4.detail.consecutive_failures} {t4.detail.loops_done}")

# The counter used to do a second job: it was the only thing stopping a loop
# that fails instantly from retrying forever. That job now belongs here.
from bot.engine.scheduler import scheduler
from uma_it.task import MAX_CONSECUTIVE_FAILURES
scheduler.active = True
t5 = build_task(LOOP, 0, "counting", None, dict(REAL, loops_done=0, loop_count=0))
for _ in range(MAX_CONSECUTIVE_FAILURES):
    t5.end_task(TaskStatus.TASK_STATUS_FAILED, UmaItEndReason.TP_NOT_ENOUGH)
check(f"{MAX_CONSECUTIVE_FAILURES} failures in a row stop the loop",
      scheduler.active is False, str(scheduler.active))
check("  without any of them counting as a run", t5.detail.loops_done == 0,
      str(t5.detail.loops_done))

scheduler.active = True
t6 = build_task(LOOP, 0, "counting", None, dict(REAL, loops_done=0, loop_count=0))
for _ in range(MAX_CONSECUTIVE_FAILURES - 1):
    t6.end_task(TaskStatus.TASK_STATUS_FAILED, UmaItEndReason.TP_NOT_ENOUGH)
check("  and one short of the limit keeps running", scheduler.active is True,
      str(scheduler.active))
scheduler.active = False

# White spark requirements are nested lists of dicts, the most structured thing
# a task carries. The process soft-restarts after every career, so a rule that
# did not survive the engine's serializer would quietly become "no requirement"
# - which matches nothing, rerolls every career, and says nothing about why.
print("\nwhite spark requirements survive the restart")
RULE = [[{'name': 'URA Finale', 'stars': 2}],
        [{'name': 'Corner Recovery ○', 'stars': 2}, {'name': 'Lay Low', 'stars': 1}]]
t7 = build_task(LOOP, 1, "sparks", None, dict(REAL, spark_skill_targets=RULE))
check("the rule is read off the payload", t7.detail.spark_skill_targets == RULE,
      str(t7.detail.spark_skill_targets))
t8 = build_task(LOOP, 1, "sparks", None, serialize_umamusume_task(t7) or {})
check("  and comes back identical through the real serializer",
      t8.detail.spark_skill_targets == RULE, str(t8.detail.spark_skill_targets))
t9 = build_task(LOOP, 1, "sparks", None, REAL)
check("a task saved before the field existed restores with no requirement",
      t9.detail.spark_skill_targets == [], str(t9.detail.spark_skill_targets))

# The scheduler reads these two off the detail by name to decide when a loop is
# done. A rename here would silently make every loop unlimited.
print("\nfields the scheduler reads by name")
check("detail.loop_count exists", hasattr(t1.detail, 'loop_count'))
check("detail.loops_done exists", hasattr(t1.detail, 'loops_done'))

print(f"\n{len(failures)} failed")
sys.exit(1 if failures else 0)
