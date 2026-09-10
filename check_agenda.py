"""The agenda picker, and the one rule it exists to enforce.

Loading the wrong agenda looks exactly like loading the right one - nothing in
the logs distinguishes them, which is how fifteen careers ran a four-race
schedule. So the assertions that matter here are all negative: what the picker
must *not* click, and when.

The parse helpers are stubbed. Their pixel geometry is the parent's, moved
verbatim and unchanged; what is being checked is the decision made from what
they return, which is where every failure has been.
"""
import os, sys
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

import numpy as np

import uma_it.agenda as agenda
from uma_it.asset.point import (AGENDA_MY_AGENDAS, AGENDA_CLOSE,
                                AGENDA_OVERWRITE_CONFIRM, AGENDA_OVERWRITE_CANCEL)
from uma_it.context import CareerContext

agenda.time.sleep = lambda *_: None
failures = []

NAME = lambda p: getattr(p, 'desc', p)
BUTTONS = [(610, 500), (610, 700), (610, 900)]


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
    def __init__(self, phase='', steps=0, waits=0):
        self.ctrl = FakeCtrl()
        self.career = CareerContext()
        self.career.agenda_phase = phase
        self.career.agenda_steps = steps
        self.career.agenda_waits = waits


def stub(first_row, buttons=BUTTONS, names=('Fan',)):
    agenda.agenda_first_visible_row = lambda _img: first_row
    agenda.agenda_load_buttons = lambda _img: list(buttons)
    agenda.agenda_row_names = lambda _img, _b: list(names)


print("the rule: never load a row the scrollbar has not confirmed")
stub(first_row=None)
ctx = FakeCtx(phase='list')
agenda.script_my_agendas(ctx)
check("an unreadable scrollbar loads nothing", ctx.ctrl.clicks == [], str(ctx.ctrl.clicks))
check("  and scrolls up to look again", ctx.ctrl.swipes == ["agenda list"], str(ctx.ctrl.swipes))
check("  leaving the phase alone", ctx.career.agenda_phase == 'list', ctx.career.agenda_phase)

stub(first_row=5)
ctx = FakeCtx(phase='list')
agenda.script_my_agendas(ctx)
check("a list starting at row 5 loads nothing", ctx.ctrl.clicks == [], str(ctx.ctrl.clicks))
check("  and scrolls up", ctx.ctrl.swipes == ["agenda list"], str(ctx.ctrl.swipes))

stub(first_row=2)
ctx = FakeCtx(phase='list')
agenda.script_my_agendas(ctx)
check("even row 2 on top loads nothing", ctx.ctrl.clicks == [], str(ctx.ctrl.clicks))

print("\nand only then, row 1")
stub(first_row=1)
ctx = FakeCtx(phase='list')
agenda.script_my_agendas(ctx)
check("row 1 on top clicks the first Load List button",
      ctx.ctrl.clicks == [(610, 500, "Load agenda row 1")], str(ctx.ctrl.clicks))
check("  and moves to load_clicked", ctx.career.agenda_phase == 'load_clicked',
      ctx.career.agenda_phase)

print("\nno buttons visible at all")
stub(first_row=1, buttons=[])
ctx = FakeCtx(phase='list')
agenda.script_my_agendas(ctx)
check("nudges the list rather than clicking blind",
      ctx.ctrl.clicks == [] and ctx.ctrl.swipes == ["agenda list"],
      f"{ctx.ctrl.clicks} {ctx.ctrl.swipes}")

print("\nthe overwrite dialog, which cannot be undone")
ctx = FakeCtx(phase='load_clicked')
agenda.script_agenda_overwrite(ctx)
check("confirms the overwrite this flow asked for",
      ctx.ctrl.clicks == [NAME(AGENDA_OVERWRITE_CONFIRM)], str(ctx.ctrl.clicks))
check("  and moves to loaded", ctx.career.agenda_phase == 'loaded', ctx.career.agenda_phase)

for phase in ('', 'list', 'done', 'loaded'):
    ctx = FakeCtx(phase=phase)
    agenda.script_agenda_overwrite(ctx)
    check(f"cancels an overwrite it did not ask for (phase {phase!r})",
          ctx.ctrl.clicks == [NAME(AGENDA_OVERWRITE_CANCEL)], str(ctx.ctrl.clicks))

print("\nthe editor")
stub(first_row=1)
ctx = FakeCtx(phase='opening')
agenda.script_agenda(ctx)
check("'opening' goes on to the slot list",
      ctx.ctrl.clicks == [NAME(AGENDA_MY_AGENDAS)], str(ctx.ctrl.clicks))
check("  and moves to list", ctx.career.agenda_phase == 'list', ctx.career.agenda_phase)

ctx = FakeCtx(phase='loaded')
agenda.script_agenda(ctx)
check("'loaded' closes the editor", ctx.ctrl.clicks == [NAME(AGENDA_CLOSE)],
      str(ctx.ctrl.clicks))
check("  and finishes", ctx.career.agenda_phase == 'done', ctx.career.agenda_phase)

ctx = FakeCtx(phase='')
agenda.script_agenda(ctx)
check("an editor with nothing in flight is closed",
      ctx.ctrl.clicks == [NAME(AGENDA_CLOSE)], str(ctx.ctrl.clicks))

print("\nthe misread that the button count settles")
# 'Agenda' and 'My Agendas' are 0.75 similar. When the title says editor but
# the Load List buttons are there, the list is really up.
stub(first_row=1)
ctx = FakeCtx(phase='list')
agenda.script_agenda(ctx)
check("a mistitled slot list is handled as the slot list",
      ctx.ctrl.clicks == [(610, 500, "Load agenda row 1")], str(ctx.ctrl.clicks))

print("\nthe budgets, which stop a stuck flow short of the click guard")
stub(first_row=1)
ctx = FakeCtx(phase='list', steps=agenda.AGENDA_MAX_STEPS)
agenda.script_my_agendas(ctx)
check("gives up once the step budget is spent", ctx.career.agenda_phase == 'done',
      ctx.career.agenda_phase)
check("  by closing, not by loading a row",
      ctx.ctrl.clicks == [NAME(AGENDA_CLOSE)], str(ctx.ctrl.clicks))

ctx = FakeCtx(phase='load_clicked', waits=0)
agenda.script_agenda(ctx)
check("waits out the gap before the overwrite dialog", ctx.ctrl.clicks == [],
      str(ctx.ctrl.clicks))
ctx = FakeCtx(phase='load_clicked', waits=99)
agenda.script_agenda(ctx)
check("  then reopens the list once the wait budget is spent",
      ctx.ctrl.clicks == [NAME(AGENDA_MY_AGENDAS)] and ctx.career.agenda_phase == 'list',
      f"{ctx.ctrl.clicks} {ctx.career.agenda_phase}")

print(f"\n{len(failures)} failed")
sys.exit(1 if failures else 0)
