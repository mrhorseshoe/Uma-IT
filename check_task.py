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
import os, sys, time
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

# The 3* override is blue-only by design, and the coercion is where that is
# enforced. A pink name stored here would be a setting that reads as configured
# on the dashboard and can never fire, because the check only reads blue rows.
# Out of legacy borrows is neither a run nor a failure - nothing started - but
# nothing will start until the borrows reset, so the loop has to stop and stay
# stopped across the soft restart.
print("\nrunning out of legacy borrows stops the loop")
from bot.engine.scheduler import scheduler as _sched
_was = _sched.active
_sched.active = True
_t = build_task(LOOP, 1, "legacy", None, dict(REAL, loops_done=4, consecutive_failures=0))
_t.end_task(TaskStatus.TASK_STATUS_FAILED, UmaItEndReason.NO_LEGACY_BORROWS)
check("the scheduler is stopped", _sched.active is False, str(_sched.active))
check("  no run is counted", _t.detail.loops_done == 4, str(_t.detail.loops_done))
check("  and it is not a failure", _t.detail.consecutive_failures == 0,
      str(_t.detail.consecutive_failures))
_sched.active = _was

print("\nthe 3* blue override is coerced to blue sparks")
t9a = build_task(LOOP, 1, "sparks", None,
                 dict(REAL, spark_keep_3star=['Stamina', 'power']))
check("blue names are kept, and capitalised the way the page offers them",
      t9a.detail.spark_keep_3star == ['Stamina', 'Power'],
      str(t9a.detail.spark_keep_3star))
t9b = build_task(LOOP, 1, "sparks", None,
                 dict(REAL, spark_keep_3star=['Turf', 'Nonsense', 'Speed', 'speed']))
check("  anything that is not a blue spark is dropped, duplicates with it",
      t9b.detail.spark_keep_3star == ['Speed'], str(t9b.detail.spark_keep_3star))
t9c = build_task(LOOP, 1, "sparks", None, serialize_umamusume_task(t9a) or {})
check("  and the list survives the restart",
      t9c.detail.spark_keep_3star == ['Stamina', 'Power'],
      str(t9c.detail.spark_keep_3star))
t9d = build_task(LOOP, 1, "sparks", None, REAL)
check("a task saved before the field existed restores with no override",
      t9d.detail.spark_keep_3star == [], str(t9d.detail.spark_keep_3star))

# Being short of TP is not a failed career: the run never started, and TP comes
# back on its own. Counted as failures, three of them stopped a healthy loop in
# 25 seconds on 19 Sep - the last attempt was 1 TP short.
print("\nwaiting for TP rather than failing")
t12 = build_task(LOOP, 0, "tp", None, dict(REAL, loops_done=5, loop_count=0,
                                           consecutive_failures=1))
t12.detail.resume_after = int(time.time()) + 900
t12.end_task(TaskStatus.TASK_STATUS_FAILED, UmaItEndReason.TP_WAIT)
check("a TP wait is not counted as a failure", t12.detail.consecutive_failures == 1,
      str(t12.detail.consecutive_failures))
check("  nor as a run", t12.detail.loops_done == 5, str(t12.detail.loops_done))
# Elapsed, not the sum of the waits it planned. A wait cut short - by a team
# trials session, or a restart - used to count in full: on 19 Sep the loop had
# clocked 210 minutes of waiting against 150 minutes of being short of TP,
# which would have stopped it two hours early.
check("  the clock starts on the first wait", t12.detail.tp_wait_since > 0,
      str(t12.detail.tp_wait_since))
check("  and counts elapsed time, not the wait it asked for",
      t12.detail.tp_waited_seconds < 60, str(t12.detail.tp_waited_seconds))
t12.detail.tp_wait_since = int(time.time()) - 3600
t12.end_task(TaskStatus.TASK_STATUS_FAILED, UmaItEndReason.TP_WAIT)
check("  so an hour short of TP reads as an hour",
      3600 <= t12.detail.tp_waited_seconds <= 3660, str(t12.detail.tp_waited_seconds))
back = build_task(LOOP, 0, "tp", None, serialize_umamusume_task(t12) or {})
check("  the resume time survives the restart",
      back.detail.resume_after == t12.detail.resume_after, str(back.detail.resume_after))
t12.start_task()
check("  and starting a run clears it", t12.detail.resume_after == 0,
      str(t12.detail.resume_after))
t12.end_task(TaskStatus.TASK_STATUS_SUCCESS, EndTaskReason.COMPLETE)
check("  a completed career forgets the waiting",
      t12.detail.tp_waited_seconds == 0 and t12.detail.tp_wait_since == 0,
      f"{t12.detail.tp_waited_seconds} {t12.detail.tp_wait_since}")

# The scheduler is what actually holds the loop back.
from bot.engine.scheduler import scheduler as sched
from uma_it.task import MAX_TP_WAIT_SECONDS


class FakeExecutor:
    active = False

    def __init__(self):
        self.started = []

    def start(self, *tasks):
        self.started.append(tasks)


t13 = build_task(LOOP, 0, "tp", None, dict(REAL, loops_done=1, loop_count=0))
t13.task_status = TaskStatus.TASK_STATUS_PENDING
t13.detail.resume_after = int(time.time()) + 600
sched.task_list = [t13]
sched.active = True
sched.stop_after_run = False
fe = FakeExecutor()
sched.tick(fe)
check("the scheduler starts nothing while the wait stands", fe.started == [],
      str(fe.started))
t13.detail.resume_after = int(time.time()) - 1
sched.tick(fe)
time.sleep(0.3)
check("  and starts the next career once it passes", len(fe.started) == 1,
      str(fe.started))
sched.active = False
sched.task_list = []

# A few points short is worth waiting for; a whole working day short is a
# different problem and should say so rather than retry into the evening.
sched.active = True
t14 = build_task(LOOP, 0, "tp", None, dict(REAL, loops_done=1, loop_count=0))
t14.detail.tp_wait_since = int(time.time()) - MAX_TP_WAIT_SECONDS
t14.end_task(TaskStatus.TASK_STATUS_FAILED, UmaItEndReason.TP_WAIT)
check(f"waiting {MAX_TP_WAIT_SECONDS // 3600}h for TP stops the loop",
      sched.active is False, str(sched.active))
sched.active = False

# Runs whose kept sparks met every requirement, shown on the dashboard. Bumped
# at the spark decision and written by the same end-of-run save as loops_done.
print("\nthe spark goal counter")
t10 = build_task(LOOP, 1, "sparks", None, REAL)
check("a task saved before the counter existed starts it at 0",
      t10.detail.spark_goal_runs == 0, str(t10.detail.spark_goal_runs))
t10.detail.spark_goal_runs = 3
t11 = build_task(LOOP, 1, "sparks", None, serialize_umamusume_task(t10) or {})
check("  and a count survives the restart", t11.detail.spark_goal_runs == 3,
      str(t11.detail.spark_goal_runs))

# The scheduler reads these two off the detail by name to decide when a loop is
# done. A rename here would silently make every loop unlimited.
print("\nfields the scheduler reads by name")
check("detail.loop_count exists", hasattr(t1.detail, 'loop_count'))
check("detail.loops_done exists", hasattr(t1.detail, 'loops_done'))

print(f"\n{len(failures)} failed")
sys.exit(1 if failures else 0)
