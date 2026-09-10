"""Restoring TP: the one flow in this app that spends on purpose.

Each step recognises its own screen, so the assertions are one per screen plus
the two rules that decide what gets spent:

* a TP item is preferred over carats, but
* a **chocolate** TP item is never spent - those are event items people keep,
  and carats are the cheaper thing to lose.

The screen matching is stubbed. What is checked is which click each recognised
screen produces, and that an unrecognised one gives up rather than being
retried into the repetitive-click guard.
"""
import os, sys
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

import numpy as np

import uma_it.tp as tp
from uma_it.asset.point import (TO_RECOVER_TP, USE_TP_DRINK, USE_CARROT_RECOVER_TP,
                                USE_TP_DRINK_CONFIRM, USE_CARROT_RECOVER_TP_ADD,
                                USE_CARROT_RECOVER_CONFIRM, USE_TP_DRINK_RESULT_CLOSE)
from uma_it.context import CareerContext
from uma_it.task import build_task
from bot.base.task import TaskExecuteMode

tp.time.sleep = lambda *_: None
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
    def __init__(self, **settings):
        self.ctrl = FakeCtrl()
        self.career = CareerContext()
        self.current_screen = np.zeros((1280, 720, 3), np.uint8)
        self.task = build_task(TaskExecuteMode.TASK_EXECUTE_MODE_LOOP, 1,
                               "check", None, settings)


def on_screen(*names):
    """Pretend exactly these templates match."""
    wanted = set(names)
    tp.image_match = lambda _img, tmpl: type(
        'M', (), {'find_match': getattr(tmpl, 'template_name', '') in wanted})()


print("whether it may spend at all")
check("allow_recover_tp 0 means no", tp.allowed(FakeCtx(allow_recover_tp=0)) is False)
check("anything above 0 means yes", tp.allowed(FakeCtx(allow_recover_tp=2)) is True)

print("\nthe selection screen")
tp.ocr_line = lambda _img: "Juice"
on_screen('RECOVER_TP_1', 'TP_RECOVER_DRINK')
ctx = FakeCtx(allow_recover_tp=2)
tp.step(ctx)
check("prefers a TP item when one is held",
      ctx.ctrl.clicks == [NAME(USE_TP_DRINK)], str(ctx.ctrl.clicks))

on_screen('RECOVER_TP_1')          # no drink template = no item on offer
ctx = FakeCtx(allow_recover_tp=2)
tp.step(ctx)
check("falls back to carats when none is held",
      ctx.ctrl.clicks == [NAME(USE_CARROT_RECOVER_TP)], str(ctx.ctrl.clicks))

print("\n  and never spends a chocolate item")
tp.ocr_line = lambda _img: "Chocolate Carrot"
on_screen('RECOVER_TP_1', 'TP_RECOVER_DRINK')
ctx = FakeCtx(allow_recover_tp=2)
tp.step(ctx)
check("a chocolate item on the row is skipped for carats",
      ctx.ctrl.clicks == [NAME(USE_CARROT_RECOVER_TP)], str(ctx.ctrl.clicks))

tp.ocr_line = lambda _img: "Juice"
ctx = FakeCtx(allow_recover_tp=2)
tp.step(ctx, body_text="use your choc carrot?")
check("  and so is one named only in the dialog body",
      ctx.ctrl.clicks == [NAME(USE_CARROT_RECOVER_TP)], str(ctx.ctrl.clicks))

print("\nthe confirms, which differ by what is being spent")
on_screen('RECOVER_TP_2')
ctx = FakeCtx(allow_recover_tp=2)
tp.step(ctx)
check("the item confirm", ctx.ctrl.clicks == [NAME(USE_TP_DRINK_CONFIRM)],
      str(ctx.ctrl.clicks))

on_screen('RECOVER_TP_2_CARROT')
ctx = FakeCtx(allow_recover_tp=2)
tp.step(ctx)
check("the carat confirm takes two clicks",
      ctx.ctrl.clicks == [NAME(USE_CARROT_RECOVER_TP_ADD),
                          NAME(USE_CARROT_RECOVER_CONFIRM)], str(ctx.ctrl.clicks))

print("\nthe result")
for name in ('RECOVER_TP_3', 'RECOVER_TP_3_CARROT'):
    on_screen(name)
    ctx = FakeCtx(allow_recover_tp=2)
    ctx.career.tp_recover_tries = 4
    tp.step(ctx)
    check(f"{name} is closed", ctx.ctrl.clicks == [NAME(USE_TP_DRINK_RESULT_CLOSE)],
          str(ctx.ctrl.clicks))
    check("  and the step count resets", ctx.career.tp_recover_tries == 0,
          str(ctx.career.tp_recover_tries))

print("\nthe prompt, when no step screen matches")
on_screen()
ctx = FakeCtx(allow_recover_tp=2)
tp.step(ctx, body_text="you need 12 more tp. restore tp?")
check("opens the recovery screen", ctx.ctrl.clicks == [NAME(TO_RECOVER_TP)],
      str(ctx.ctrl.clicks))

print("\ngiving up rather than feeding the click guard")
ctx = FakeCtx(allow_recover_tp=2)
ctx.career.tp_recover_tries = tp.MAX_STEPS
check("returns False once the step budget is spent", tp.step(ctx) is False)
check("  having clicked nothing", ctx.ctrl.clicks == [], str(ctx.ctrl.clicks))

ctx = FakeCtx(allow_recover_tp=2)
check("an unrecognised screen with unrelated body text gives up",
      tp.step(ctx, body_text="something else entirely") is False)

print(f"\n{len(failures)} failed")
sys.exit(1 if failures else 0)
