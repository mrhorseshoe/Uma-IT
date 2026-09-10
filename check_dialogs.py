"""What the router actually does with a frame.

Drives `script_dialog` with a fake controller and a scripted title, and asserts
on the clicks it records. No emulator, no screenshots - the title read is the
only input that matters, so it is supplied directly.

The cases here are the ones where being wrong is expensive: the TP decision
that ends the loop, the screens the parent deliberately does not click, and the
career-start dialogs whose handlers are not written yet and must therefore stay
still.
"""
import os, sys
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

import uma_it.dialogs as dialogs
from uma_it.asset.point import (ESCAPE, TO_RECOVER_TP, CULTIVATE_FINISH_RETURN_CONFIRM,
                                TO_CULTIVATE_PREPARE_NEXT)
from uma_it.context import CareerContext
from uma_it.task import build_task, EndTaskReason
from bot.base.task import TaskExecuteMode, TaskStatus

dialogs.time.sleep = lambda *_: None   # the router sleeps 1s after each click

failures = []


def check(label, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'}  {label}{'' if cond else '   ' + detail}")
    if not cond:
        failures.append(label)


class FakeCtrl:
    def __init__(self):
        self.clicks = []

    def click_by_point(self, point):
        self.clicks.append(getattr(point, 'desc', point))

    def click(self, x, y, name):
        self.clicks.append((x, y, name))


class FakeCtx:
    def __init__(self, **settings):
        self.ctrl = FakeCtrl()
        self.career = CareerContext()
        self.current_screen = None
        self.task = build_task(TaskExecuteMode.TASK_EXECUTE_MODE_LOOP, 1,
                               "check", None, settings)
        self.ended = []
        self.task.end_task = lambda status, reason: self.ended.append((status, reason))


def route(title, **settings):
    """Run one frame through the router with the title read already decided."""
    ctx = FakeCtx(**settings)
    dialogs.read_title = lambda _ctx: title
    dialogs.script_dialog(ctx)
    return ctx


NAME = lambda p: getattr(p, 'desc', p)

print("screens the parent cleared blindly, now named")
for title in ('Perks', 'Borrow Card', 'Follow Trainer', 'Notices'):
    ctx = route(title)
    check(f"{title!r} makes exactly the fallback's click",
          ctx.ctrl.clicks == [NAME(ESCAPE)], str(ctx.ctrl.clicks))

print("\nending a career")
ctx = route('Career Complete')
check("'Career Complete' cancels the return prompt",
      ctx.ctrl.clicks == [NAME(CULTIVATE_FINISH_RETURN_CONFIRM)], str(ctx.ctrl.clicks))

print("\nthe TP decision, which is how the loop stops")
ctx = route('Confirm', allow_recover_tp=0)
check("declines when allow_recover_tp is 0", ctx.ctrl.clicks == [], str(ctx.ctrl.clicks))
check("  and fails the career", [s for s, _ in ctx.ended] == [TaskStatus.TASK_STATUS_FAILED],
      str(ctx.ended))
check("  for the right reason",
      [r for _, r in ctx.ended] == [EndTaskReason.TP_NOT_ENOUGH], str(ctx.ended))

ctx = route('Confirm', allow_recover_tp=2)
check("accepts when the task authorises spending",
      ctx.ctrl.clicks == [NAME(TO_RECOVER_TP)], str(ctx.ctrl.clicks))
check("  and does not end the career", ctx.ended == [], str(ctx.ended))

print("\nscreens the parent knows and deliberately does not click")
for title in ('Recover TP', 'Items Selected'):
    ctx = route(title)
    check(f"{title!r} clicks nothing", ctx.ctrl.clicks == [], str(ctx.ctrl.clicks))

print("\nthe parents picker")
ctx = route('Auto Select', use_last_parents=True)
check("'Auto Select' keeps the last parents when asked",
      ctx.ctrl.clicks == [NAME(TO_CULTIVATE_PREPARE_NEXT)], str(ctx.ctrl.clicks))
ctx = route('Auto Select', use_last_parents=False)
check("  and lets the game choose otherwise",
      ctx.ctrl.clicks == [(214, 832, "Auto Select")], str(ctx.ctrl.clicks))

print("\ncareer-start dialogs whose handlers are not written")
for title in ('Final Confirmation', 'Independent Training', 'Choose Career Mode',
              'Start Event'):
    ctx = route(title)
    check(f"{title!r} stays still", ctx.ctrl.clicks == [], str(ctx.ctrl.clicks))

print("\nthe agenda titles reach the picker")
# What the picker then does is check_agenda.py's business. This pins only that
# the router hands these three to it, rather than clearing them like a stray
# dialog - which would abandon the flow mid-way and start the run on whatever
# schedule the game happened to have.
import uma_it.agenda as agenda_mod

reached = []
for title, fn in (('Agenda', 'script_agenda'),
                  ('My Agendas', 'script_my_agendas'),
                  ('Overwrite', 'script_agenda_overwrite')):
    original = dialogs.DIALOGS[title]
    dialogs.DIALOGS[title] = lambda _ctx, _t=title: reached.append(_t)
    route(title)
    dialogs.DIALOGS[title] = original
    check(f"{title!r} is routed to agenda.py",
          getattr(original, '__module__', '') == agenda_mod.__name__,
          getattr(original, '__module__', '?'))
check("  and all three were dispatched",
      reached == ['Agenda', 'My Agendas', 'Overwrite'], str(reached))

print("\nan unknown title")
ctx = route('Qwerty Nonsense Title')
check("still gets the load-bearing fallback click",
      ctx.ctrl.clicks == [NAME(ESCAPE)], str(ctx.ctrl.clicks))

print("\nthe repeat counter, which tells a stuck dialog from stacked prompts")
ctx = FakeCtx()
dialogs.read_title = lambda _ctx: 'Perks'
for _ in range(3):
    dialogs.script_dialog(ctx)
check("counts consecutive frames of the same dialog", ctx.career.dialog_repeat == 3,
      str(ctx.career.dialog_repeat))
dialogs.read_title = lambda _ctx: 'Notices'
dialogs.script_dialog(ctx)
check("  and resets when a different dialog appears", ctx.career.dialog_repeat == 1,
      str(ctx.career.dialog_repeat))

print("\nthe blind fallback for a frame matching no screen")
ctx = FakeCtx()
dialogs.script_not_found_ui(ctx)
check("clicks the corner under a fixed name",
      ctx.ctrl.clicks == [(719, 1, "Default fallback click")], str(ctx.ctrl.clicks))

print(f"\n{len(failures)} failed")
sys.exit(1 if failures else 0)
