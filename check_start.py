"""Career start, where a wrong click cannot be taken back.

Three dialogs, three ways to lose a career:

* confirming the career-mode dialog on the event option starts an event run,
  and there is no way out of one;
* confirming the start dialog on the wrong tab plays a turn-by-turn career this
  app has no handlers for;
* clicking blind on the pending-run dialog can hit Delete Data, which is on the
  same screen as the button that resumes the career.

So the assertions here are about when each handler refuses to act. The
screen-reading is stubbed - it is the parent's, moved verbatim - and what is
checked is the decision made from what it returns.

**None of this has run against the live game.** These checks say the logic is
right; they cannot say the tab template still matches after a game update.
"""
import os, sys
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

import numpy as np

import uma_it.start as start
import uma_it.agenda as agenda
from uma_it.asset.point import (CAREER_MODE_NORMAL, CAREER_MODE_CONFIRM,
                                CULTIVATE_FINAL_CHECK_START, AGENDA_EDIT,
                                FINAL_CONFIRMATION_TAB_INDEPENDENT,
                                INDEPENDENT_TRAINING_PENDING_CAREER)
from uma_it.context import CareerContext
from uma_it.task import build_task
from bot.base.task import TaskExecuteMode, TaskStatus, EndTaskReason

start.time.sleep = lambda *_: None
agenda.time.sleep = lambda *_: None

# Kept before the stubs below replace it, so the real reader can be checked.
real_event_mode_selected = start._event_mode_selected

failures = []
NAME = lambda p: getattr(p, 'desc', p)


def check(label, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'}  {label}{'' if cond else '   ' + detail}")
    if not cond:
        failures.append(label)


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
    def __init__(self, **career_state):
        self.ctrl = FakeCtrl()
        self.career = CareerContext()
        for k, v in career_state.items():
            setattr(self.career, k, v)
        self.current_screen = np.zeros((1280, 720, 3), np.uint8)
        self.task = build_task(TaskExecuteMode.TASK_EXECUTE_MODE_LOOP, 1, "check", None, {})
        self.ended = []
        self.task.end_task = lambda s, r: self.ended.append((s, r))


print("the career-mode dialog: confirm is a one-way door")
start._event_mode_selected = lambda _ctx: True
ctx = FakeCtx()
start.script_choose_career_mode(ctx)
check("event mode selected switches to Normal, never confirms",
      ctx.ctrl.clicks == [NAME(CAREER_MODE_NORMAL)], str(ctx.ctrl.clicks))
check("  and counts the attempt", ctx.career.career_mode_switch_tries == 1,
      str(ctx.career.career_mode_switch_tries))

ctx = FakeCtx(career_mode_switch_tries=start.MAX_CAREER_MODE_SWITCHES)
start.script_choose_career_mode(ctx)
check("gives up rather than confirming once the budget is spent",
      ctx.ctrl.clicks == [], str(ctx.ctrl.clicks))
check("  by failing the task", [s for s, _ in ctx.ended] == [TaskStatus.TASK_STATUS_FAILED],
      str(ctx.ended))

start._event_mode_selected = lambda _ctx: False
ctx = FakeCtx(career_mode_switch_tries=3)
start.script_choose_career_mode(ctx)
check("confirms only once Normal Mode is verified",
      ctx.ctrl.clicks == [NAME(CAREER_MODE_CONFIRM)], str(ctx.ctrl.clicks))
check("  and clears the attempt count", ctx.career.career_mode_switch_tries == 0,
      str(ctx.career.career_mode_switch_tries))

print("\n  an unreadable frame must not be read as 'safe to confirm'")


class Exploding:
    def get_screen(self, to_gray=False):
        raise RuntimeError("no screen")


ctx = FakeCtx()
ctx.ctrl = Exploding()
check("an unreadable career-mode dialog counts as event mode",
      real_event_mode_selected(ctx) is True)

print("\nthe start dialog: the tab is checked, not assumed")
start.image_match = lambda *_a, **_k: type('M', (), {'find_match': False})()
ctx = FakeCtx()
start.script_final_confirmation(ctx)
check("the wrong tab is switched, not confirmed",
      ctx.ctrl.clicks == [NAME(FINAL_CONFIRMATION_TAB_INDEPENDENT)], str(ctx.ctrl.clicks))

ctx = FakeCtx(final_confirmation_tab_tries=start.MAX_TAB_SWITCHES)
start.script_final_confirmation(ctx)
check("after the budget it starts rather than tapping into the click guard",
      ctx.ctrl.clicks == [NAME(CULTIVATE_FINAL_CHECK_START)], str(ctx.ctrl.clicks))

start.image_match = lambda *_a, **_k: type('M', (), {'find_match': True})()
ctx = FakeCtx()
start.script_final_confirmation(ctx)
check("the right tab hands off to the agenda picker first",
      ctx.ctrl.clicks == [NAME(AGENDA_EDIT)], str(ctx.ctrl.clicks))
check("  by setting the phase agenda.py runs on",
      ctx.career.agenda_phase == 'opening', ctx.career.agenda_phase)

start.agenda_schedule_counts = lambda _img: {'scheduled': 47, 'g1': 23, 'g2': 11, 'g3': 11}
ctx = FakeCtx(agenda_phase='done')
start.script_final_confirmation(ctx)
check("a finished agenda flow confirms the start",
      ctx.ctrl.clicks == [NAME(CULTIVATE_FINAL_CHECK_START)], str(ctx.ctrl.clicks))

start.agenda_schedule_counts = lambda _img: None
ctx = FakeCtx(agenda_phase='done')
start.script_final_confirmation(ctx)
check("  and still confirms when the race counts cannot be read",
      ctx.ctrl.clicks == [NAME(CULTIVATE_FINAL_CHECK_START)], str(ctx.ctrl.clicks))


def boom(_img):
    raise RuntimeError("OCR exploded")


start.agenda_schedule_counts = boom
ctx = FakeCtx(agenda_phase='done')
start.script_final_confirmation(ctx)
check("  and when reading them raises",
      ctx.ctrl.clicks == [NAME(CULTIVATE_FINAL_CHECK_START)], str(ctx.ctrl.clicks))

print("\nthe pending-run dialog: Delete Data is on the same screen")
start.find_green_button = lambda *_a: (360, 830)
ctx = FakeCtx()
start.script_independent_training_pending(ctx, ((0, 0), (0, 400)))
check("enters at the green button the colour search found",
      ctx.ctrl.clicks == [(360, 830, "Enter the pending Independent Training run")],
      str(ctx.ctrl.clicks))

start.find_green_button = lambda *_a: None
ctx = FakeCtx()
start.script_independent_training_pending(ctx, ((0, 0), (0, 400)))
check("falls back to the fixed point when the search fails",
      ctx.ctrl.clicks == [NAME(INDEPENDENT_TRAINING_PENDING_CAREER)], str(ctx.ctrl.clicks))

ctx = FakeCtx(pending_run_tries=start.MAX_PENDING_ENTRIES)
start.script_independent_training_pending(ctx, ((0, 0), (0, 400)))
check("stops clicking once the budget is spent", ctx.ctrl.clicks == [],
      str(ctx.ctrl.clicks))

print(f"\n{len(failures)} failed")
sys.exit(1 if failures else 0)
