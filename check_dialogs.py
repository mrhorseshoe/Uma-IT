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

import numpy as np

import uma_it.dialogs as dialogs
from uma_it.asset.point import (ESCAPE, RESTORE_NO, TO_RECOVER_TP, CULTIVATE_FINISH_RETURN_CONFIRM,
                                TO_CULTIVATE_PREPARE_NEXT,
                                EXIT_WITHOUT_LEARNING_SKILLS_OK)
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

    def get_screen(self, to_gray=False):
        return np.zeros((1280, 720, 3), np.uint8)

    def click_by_point(self, point):
        self.clicks.append(getattr(point, 'desc', point))

    def click(self, x, y, name):
        self.clicks.append((x, y, name))


class FakeCtx:
    def __init__(self, **settings):
        self.ctrl = FakeCtrl()
        self.career = CareerContext()
        self.current_screen = np.zeros((1280, 720, 3), np.uint8)
        self.task = build_task(TaskExecuteMode.TASK_EXECUTE_MODE_LOOP, 1,
                               "check", None, settings)
        self.ended = []
        self.task.end_task = lambda status, reason: self.ended.append((status, reason))


def route(title, body='', **settings):
    """Run one frame through the router with the title read already decided.

    `body` matters only for 'Confirm', the one title the game reuses across
    unrelated prompts.
    """
    ctx = FakeCtx(**settings)
    dialogs.read_title = lambda _ctx: title
    dialogs.read_body = lambda _ctx, _pos: body
    ctx.career.dialog_header_pos = ((8, 391), (136, 440))
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

print("\nthe TP decision, which now holds the loop instead of stopping it")
import time as _time
ctx = route('Confirm', body='You need 2 more TP to start a Career Scenario.',
            allow_recover_tp=0)
# The prompt is modal, so declining is not optional: a run that ends with it
# still up leaves the game behind a popup nothing else can get past.
check("declines when allow_recover_tp is 0",
      ctx.ctrl.clicks == [NAME(RESTORE_NO)], str(ctx.ctrl.clicks))
check("  and ends the run", [s for s, _ in ctx.ended] == [TaskStatus.TASK_STATUS_FAILED],
      str(ctx.ended))
# As TP_NOT_ENOUGH this counted as a failure, and three in a row stop the loop:
# on 19 Sep that ended a session while the game was asking for one more TP.
check("  as a TP wait, not a failure",
      [r for _, r in ctx.ended] == [EndTaskReason.TP_WAIT], str(ctx.ended))
waited = ctx.task.detail.resume_after - int(_time.time())
check("  and holds the next run for the shortfall (2 TP -> ~21 min)",
      1200 <= waited <= 1320, str(waited))

ctx = route('Confirm', allow_recover_tp=2)
check("accepts when the task authorises spending",
      ctx.ctrl.clicks == [NAME(TO_RECOVER_TP)], str(ctx.ctrl.clicks))
check("  and does not end the career", ctx.ended == [], str(ctx.ended))

# 'Confirm' is also the skill screen's exit prompt, raised by the Back click
# `skills._leave` makes itself. Reading that as a TP offer ended every career of
# the 11 Sep run the moment its skills were bought - three loops in three
# minutes, each re-entering the skill screen the last had never left. The title
# was matched correctly; a title is simply not enough to tell them apart.
print("\n'Confirm' is two prompts, told apart by body text")
ctx = route('Confirm', body='Exit without learning skills?', allow_recover_tp=0)
check("the skill exit prompt is confirmed",
      ctx.ctrl.clicks == [NAME(EXIT_WITHOUT_LEARNING_SKILLS_OK)], str(ctx.ctrl.clicks))
check("  and the career is not failed over it", ctx.ended == [], str(ctx.ended))

ctx = route('Confirm', body='Exit without learning skills?', allow_recover_tp=2)
check("  nor is it mistaken for TP with spending on",
      ctx.ctrl.clicks == [NAME(EXIT_WITHOUT_LEARNING_SKILLS_OK)], str(ctx.ctrl.clicks))

ctx = route('Confirm', body='Restore TP?', allow_recover_tp=0)
check("a 'Confirm' that is not about skills still ends the loop",
      [s for s, _ in ctx.ended] == [TaskStatus.TASK_STATUS_FAILED], str(ctx.ended))

print("\nand the screen behind the prompt is driven, not left sitting")
# This is where the parent stops: its handler for the Recover TP screen is
# commented out, so its logs carry 332 'Recover TP' frames with nothing acting
# on them. Here both the prompt and the screen go to the same stepper.
ctx = route('Recover TP', allow_recover_tp=2)
check("'Recover TP' with spending on takes a step",
      ctx.ctrl.clicks == [NAME(TO_RECOVER_TP)], str(ctx.ctrl.clicks))
ctx = route('Recover TP', allow_recover_tp=0)
check("  and clicks nothing with spending off", ctx.ctrl.clicks == [],
      str(ctx.ctrl.clicks))

print("\na screen the parent knows and deliberately does not click")
ctx = route('Items Selected')
check("'Items Selected' clicks nothing", ctx.ctrl.clicks == [], str(ctx.ctrl.clicks))

print("\nthe parents picker")
ctx = route('Auto Select', use_last_parents=True)
check("'Auto Select' keeps the last parents when asked",
      ctx.ctrl.clicks == [NAME(TO_CULTIVATE_PREPARE_NEXT)], str(ctx.ctrl.clicks))
ctx = route('Auto Select', use_last_parents=False)
check("  and lets the game choose otherwise",
      ctx.ctrl.clicks == [(214, 832, "Auto Select")], str(ctx.ctrl.clicks))

print("\nthe event start dialog is always backed out of")
# The only one of the career-start group that acts here rather than in
# start.py. Confirming it would begin an event career with no way out.
ctx = route('Start Event')
check("'Start Event' clears the dialog", ctx.ctrl.clicks == [NAME(ESCAPE)],
      str(ctx.ctrl.clicks))

print("\nthe career-start titles reach start.py")
# What those handlers then do is check_start.py's business; this pins only that
# the router hands them over rather than clearing them like a stray dialog.
import uma_it.start as start_mod

reached = []
for title in ('Final Confirmation', 'Independent Training', 'Choose Career Mode'):
    original = dialogs.DIALOGS[title]
    dialogs.DIALOGS[title] = lambda _ctx, _t=title: reached.append(_t)
    route(title)
    dialogs.DIALOGS[title] = original
check("all three dispatch into start.py",
      reached == ['Final Confirmation', 'Independent Training', 'Choose Career Mode'],
      str(reached))

# The pending-run handler needs the dialog header's position to bound its
# colour search. read_title stashes it; a wrong shape here would send the
# search at the whole screen, where Delete Data lives.
seen = []
original = dialogs.DIALOGS['Independent Training']
start_mod.script_independent_training_pending = lambda _ctx, pos: seen.append(pos)
ctx = FakeCtx()
ctx.career.dialog_header_pos = ((8, 391), (136, 440))
dialogs.read_title = lambda _ctx: 'Independent Training'
dialogs.DIALOGS['Independent Training'](ctx)
check("the pending-run handler is given the header position",
      seen == [((8, 391), (136, 440))], str(seen))

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

# A screen the blind click cannot advance is a trap: the clicks trip the
# repetitive-click guard, the guard restarts the game, and the game comes back
# to the same screen. On 19 Sep a team trials session left the bot on one and
# it clicked for five hours, freed only by a daily-reset dialog it knew.
print("\nthe blind fallback has a way out of a screen it cannot advance")
from uma_it.asset.point import HOME_TAB
ctx = route('nothing-matches-this-title')
ctx.ctrl.clicks.clear()
ctx.career.unknown_frames = dialogs.UNKNOWN_FRAMES_BEFORE_HOME - 1
dialogs.script_not_found_ui(ctx)
check("a minute of unrecognised frames presses Home",
      ctx.ctrl.clicks == [NAME(HOME_TAB)], str(ctx.ctrl.clicks))
ctx.ctrl.clicks.clear()
dialogs.script_not_found_ui(ctx)
check("  and not on every frame after that",
      NAME(HOME_TAB) not in ctx.ctrl.clicks, str(ctx.ctrl.clicks))

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
