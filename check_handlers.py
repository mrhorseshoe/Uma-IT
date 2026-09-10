"""The enter and collect handlers.

Mostly these press Next, and the assertions are correspondingly plain. Three
are not:

* Home, where a stale agenda phase would make the next career run the game's
  default schedule silently - the exact failure this project keeps designing
  against;
* Scenario Select, which must fail the task rather than start a career in the
  wrong scenario;
* the finish screen, which is the only way into skill buying and gets visited
  repeatedly until a pass buys nothing.
"""
import os, sys
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

import numpy as np

import uma_it.enter as enter
import uma_it.collect as collect
from uma_it.asset.point import (TO_CULTIVATE_SCENARIO_CHOOSE, TO_CULTIVATE_PREPARE_NEXT,
                                TO_CULTIVATE_PREPARE_AUTO_SELECT,
                                TO_CULTIVATE_PREPARE_INCLUDE_GUEST,
                                TO_CULTIVATE_PREPARE_CONFIRM,
                                TO_FOLLOW_SUPPORT_CARD_SELECT,
                                CULTIVATE_FINISH_CONFIRM, CULTIVATE_RESULT_CONFIRM,
                                CULTIVATE_RECEIVE_CUP_CLOSE)
from uma_it.context import CareerContext
from uma_it.define import ScenarioType
from uma_it.task import build_task
from bot.base.task import TaskExecuteMode, TaskStatus, EndTaskReason

enter.time.sleep = lambda *_: None
failures = []
NAME = lambda p: getattr(p, 'desc', p)


def check(label, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'}  {label}{'' if cond else '   ' + detail}")
    if not cond:
        failures.append(label)


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
        self.ended = []
        self.task.end_task = lambda s, r: self.ended.append((s, r))


MATCH = lambda hit: (lambda *_a, **_k: type('M', (), {'find_match': hit})())

print("Home")
enter.find_green_button = lambda *_a: (545, 1085)
ctx = FakeCtx()
enter.script_main_menu(ctx)
check("clicks CAREER where the colour search found it",
      ctx.ctrl.clicks == [(545, 1085, "Go to Scenario Selection")], str(ctx.ctrl.clicks))

enter.find_green_button = lambda *_a: None
enter.describe_green_candidates = lambda *_a, **_k: "mask empty"
ctx = FakeCtx()
enter.script_main_menu(ctx)
check("falls back to the fixed point when the search fails",
      ctx.ctrl.clicks == [NAME(TO_CULTIVATE_SCENARIO_CHOOSE)], str(ctx.ctrl.clicks))

ctx = FakeCtx(career_state={'career_finished': True})
enter.script_main_menu(ctx)
check("a finished career ends the task", [s for s, _ in ctx.ended] ==
      [TaskStatus.TASK_STATUS_SUCCESS], str(ctx.ended))
check("  and clicks nothing on the way out", ctx.ctrl.clicks == [], str(ctx.ctrl.clicks))

# A stale 'done' here makes the next career skip the agenda entirely and run
# whatever schedule the game had - with nothing in the log to say so.
ctx = FakeCtx(career_state={'agenda_phase': 'done', 'agenda_steps': 24, 'agenda_waits': 3})
enter.script_main_menu(ctx)
check("a new career clears the last one's agenda phase",
      ctx.career.agenda_phase == '', repr(ctx.career.agenda_phase))
check("  and its counters", (ctx.career.agenda_steps, ctx.career.agenda_waits) == (0, 0),
      f"{ctx.career.agenda_steps} {ctx.career.agenda_waits}")

print("\nScenario Select")
enter.image_match = MATCH(True)
ctx = FakeCtx(scenario=ScenarioType.GRAND_CONCERT.value)
enter.script_scenario_select(ctx)
check("goes on once the scenario is on screen",
      ctx.ctrl.clicks == [NAME(TO_CULTIVATE_PREPARE_NEXT)], str(ctx.ctrl.clicks))

enter.image_match = MATCH(False)
ctx = FakeCtx(scenario=ScenarioType.GRAND_CONCERT.value)
enter.script_scenario_select(ctx)
check("swipes the whole carousel before giving up",
      len(ctx.ctrl.swipes) == enter.SCENARIO_SWIPES, str(len(ctx.ctrl.swipes)))
check("  then fails the task rather than starting the wrong scenario",
      [r for _, r in ctx.ended] == [EndTaskReason.SCENARIO_NOT_FOUND], str(ctx.ended))
check("  having clicked nothing", ctx.ctrl.clicks == [], str(ctx.ctrl.clicks))

ctx = FakeCtx(scenario=ScenarioType.UNKNOWN.value)
enter.script_scenario_select(ctx)
check("an unknown scenario fails before touching the screen",
      ctx.ctrl.clicks == [] and ctx.ctrl.swipes == [], f"{ctx.ctrl.clicks} {ctx.ctrl.swipes}")

print("\nthe legacy picker")
ctx = FakeCtx(use_last_parents=True)
enter.script_extend_umamusume_select(ctx)
check("keeps the last parents in one click",
      ctx.ctrl.clicks == [NAME(TO_CULTIVATE_PREPARE_NEXT)], str(ctx.ctrl.clicks))

ctx = FakeCtx(use_last_parents=False)
enter.script_extend_umamusume_select(ctx)
check("otherwise runs auto-select in order",
      ctx.ctrl.clicks == [NAME(TO_CULTIVATE_PREPARE_AUTO_SELECT),
                          NAME(TO_CULTIVATE_PREPARE_INCLUDE_GUEST),
                          NAME(TO_CULTIVATE_PREPARE_CONFIRM),
                          NAME(TO_CULTIVATE_PREPARE_NEXT)], str(ctx.ctrl.clicks))

print("\nthe support card deck")
enter.image_match = MATCH(True)
ctx = FakeCtx()
enter.script_support_card_select(ctx)
check("an empty borrow slot goes to the borrow list",
      ctx.ctrl.clicks == [NAME(TO_FOLLOW_SUPPORT_CARD_SELECT)], str(ctx.ctrl.clicks))

enter.image_match = MATCH(False)
ctx = FakeCtx()
enter.script_support_card_select(ctx)
check("a full deck goes straight on",
      ctx.ctrl.clicks == [NAME(TO_CULTIVATE_PREPARE_NEXT)], str(ctx.ctrl.clicks))

print("\nthe borrow list")
enter.find_support_card = lambda _ctx, _img: True
ctx = FakeCtx()
enter.script_follow_support_card_select(ctx)
check("stops the moment the card is found",
      ctx.ctrl.clicks == [] and ctx.ctrl.swipes == [], f"{ctx.ctrl.clicks} {ctx.ctrl.swipes}")

enter.find_support_card = lambda _ctx, _img: False
enter._still_on_borrow_screen = lambda _ctx, _img: False
ctx = FakeCtx()
enter.script_follow_support_card_select(ctx)
check("stops scrolling once the screen has changed underneath it",
      ctx.ctrl.swipes == [], str(ctx.ctrl.swipes))

print("\nthe result screens")
for fn, point, label in ((collect.script_cultivate_result, CULTIVATE_RESULT_CONFIRM,
                          "cultivation result"),
                         (collect.script_receive_cup, CULTIVATE_RECEIVE_CUP_CLOSE,
                          "cup")):
    ctx = FakeCtx()
    fn(ctx)
    check(f"the {label} screen is confirmed", ctx.ctrl.clicks == [NAME(point)],
          str(ctx.ctrl.clicks))

print("\nthe finish screen")
ctx = FakeCtx(skip_learn_skill=True)
collect.script_cultivate_finish(ctx)
check("with skills off it confirms", ctx.ctrl.clicks == [NAME(CULTIVATE_FINISH_CONFIRM)],
      str(ctx.ctrl.clicks))
check("  and marks the career finished", ctx.career.career_finished is True)

# With skills on, the finish screen is the way *into* the skill screen. It gets
# visited repeatedly: buying spends points, so a later pass can afford things
# an earlier one could not. A pass that selects nothing ends the sweep.
from uma_it.asset.point import CULTIVATE_FINISH_LEARN_SKILL

ctx = FakeCtx(skip_learn_skill=False)
collect.script_cultivate_finish(ctx)
check("with skills on it opens the skill screen",
      ctx.ctrl.clicks == [NAME(CULTIVATE_FINISH_LEARN_SKILL)], str(ctx.ctrl.clicks))
check("  and marks the career finished", ctx.career.career_finished is True)
check("  with a sweep in progress", ctx.career.final_skill_sweep_active is True)

ctx.ctrl.clicks.clear()
ctx.career.learn_skill_selected = True      # last pass bought something
collect.script_cultivate_finish(ctx)
check("a pass that bought something goes back for more",
      ctx.ctrl.clicks == [NAME(CULTIVATE_FINISH_LEARN_SKILL)], str(ctx.ctrl.clicks))

ctx.ctrl.clicks.clear()
ctx.career.learn_skill_selected = False     # nothing left to buy
collect.script_cultivate_finish(ctx)
check("a pass that bought nothing ends the sweep",
      ctx.ctrl.clicks == [NAME(CULTIVATE_FINISH_CONFIRM)], str(ctx.ctrl.clicks))
check("  and clears the sweep flag", ctx.career.final_skill_sweep_active is False)

ctx = FakeCtx(skip_learn_skill=True, career_state={'career_finished': True})
collect.script_cultivate_finish(ctx)
check("a repeat frame confirms again rather than stalling",
      ctx.ctrl.clicks == [NAME(CULTIVATE_FINISH_CONFIRM)], str(ctx.ctrl.clicks))

print(f"\n{len(failures)} failed")
sys.exit(1 if failures else 0)
