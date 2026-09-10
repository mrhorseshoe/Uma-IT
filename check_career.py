"""The countdown handler must not click. Ever.

That is the single property this file exists to defend. Without it the frame
falls to the blind fallback, and eleven identical consecutive clicks restart
the game - on a screen the bot sits on for fifty minutes.

So the cases here are the ways the handler could be tempted into clicking or
into raising: a normal frame, a frame it cannot read, an OCR that throws, and
a context missing the run state entirely.
"""
import os, sys
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

import numpy as np

import uma_it.career as career
from uma_it.asset.point import INDEPENDENT_TRAINING_RESULTS_OK
from uma_it.context import CareerContext

slept = []
career.time.sleep = lambda s: slept.append(s)

failures = []


def check(label, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'}  {label}{'' if cond else '   ' + detail}")
    if not cond:
        failures.append(label)


class FakeCtrl:
    def __init__(self):
        self.clicks = []

    def click_by_point(self, point):
        self.clicks.append(getattr(point, 'click_point_name', point))

    def click(self, x, y, name):
        self.clicks.append((x, y, name))

    def swipe(self, *a, **k):
        self.clicks.append(('swipe', a))


class FakeCtx:
    def __init__(self, screen=True, with_career=True):
        self.ctrl = FakeCtrl()
        self.career = CareerContext() if with_career else None
        # a real array, so the handler's slicing is exercised rather than faked
        self.current_screen = np.zeros((1280, 720, 3), np.uint8) if screen else None


def wait(reads, **kw):
    """Run one pass of the countdown handler with a scripted OCR result."""
    ctx = FakeCtx(**kw)
    career.ocr_line = reads
    slept.clear()
    career.script_wait(ctx)
    return ctx


print("the countdown handler clicks nothing")
ctx = wait(lambda _img: "0:47:12")
check("on a frame it can read", ctx.ctrl.clicks == [], str(ctx.ctrl.clicks))

ctx = wait(lambda _img: "")
check("on a frame it cannot read", ctx.ctrl.clicks == [], str(ctx.ctrl.clicks))


def boom(_img):
    raise RuntimeError("OCR exploded")


ctx = wait(boom)
check("when the OCR raises", ctx.ctrl.clicks == [], str(ctx.ctrl.clicks))

ctx = wait(lambda _img: "0:47:12", screen=False)
check("when there is no screen at all", ctx.ctrl.clicks == [], str(ctx.ctrl.clicks))

ctx = wait(lambda _img: "0:47:12", with_career=False)
check("when the context carries no run state", ctx.ctrl.clicks == [], str(ctx.ctrl.clicks))

print("\nand it waits rather than spinning")
ctx = wait(lambda _img: "0:47:12")
check(f"sleeps {career.POLL_SECONDS}s between passes", slept == [career.POLL_SECONDS],
      str(slept))

print("\nit logs on the minute, not every pass")
ctx = FakeCtx()
career.ocr_line = lambda _img: "0:47:12"
career.script_wait(ctx)
first = ctx.career.last_countdown_log
career.ocr_line = lambda _img: "0:47:03"
career.script_wait(ctx)
check("a second read in the same minute does not re-log",
      ctx.career.last_countdown_log == first, f"{first!r} -> {ctx.career.last_countdown_log!r}")
career.ocr_line = lambda _img: "0:46:58"
career.script_wait(ctx)
check("  and a new minute does", ctx.career.last_countdown_log != first,
      str(ctx.career.last_countdown_log))

print("\nit feeds the live status panel")
from bot.base.runtime_state import get_state
career.ocr_line = lambda _img: "0:12:34"
career.script_wait(FakeCtx())
state = get_state()
check("the remaining time reaches runtime_state",
      state.get('independent_training', {}).get('remaining') == "0:12:34",
      str(state.get('independent_training')))

print("\nclosing the training log")
ctx = FakeCtx()
ctx.career.last_countdown_log = "0:00"
career.script_results(ctx)
check("clicks OK exactly once",
      ctx.ctrl.clicks == [getattr(INDEPENDENT_TRAINING_RESULTS_OK, 'click_point_name',
                                  INDEPENDENT_TRAINING_RESULTS_OK)],
      str(ctx.ctrl.clicks))
check("  and clears the countdown log so the next run starts fresh",
      ctx.career.last_countdown_log == '', repr(ctx.career.last_countdown_log))

print(f"\n{len(failures)} failed")
sys.exit(1 if failures else 0)
