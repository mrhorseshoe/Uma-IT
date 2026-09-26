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
from uma_it.parse import find_green_button as _real_find_green_button
from uma_it.asset.point import (TITLE_TAP,
                                TO_CULTIVATE_SCENARIO_CHOOSE, TO_CULTIVATE_PREPARE_NEXT,
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

print("Home, against real pixels")
# The stubs below check the decision; this checks the search itself, on the
# CAREER region of an actual Home frame. It pins the region and the colour
# thresholds together - a change to either that stopped finding the button
# would otherwise only show up on the game.
import cv2

_crop = cv2.imread('resource/uma_it/fixture/home_career_region.png')
check("the fixture loads", _crop is not None)
if _crop is not None:
    _found = _real_find_green_button(_crop, 0, 0, _crop.shape[1], _crop.shape[0])
    check("the CAREER button is found in a real Home frame", _found is not None,
          str(_found))
    if _found:
        # in full-frame coordinates, for comparison with the fixed point (545, 1085)
        _abs = (enter.CAREER_REGION[0] + _found[0], enter.CAREER_REGION[1] + _found[1])
        check("  and lands on the button, near the fixed point",
              abs(_abs[0] - 545) < 40 and abs(_abs[1] - 1085) < 40, str(_abs))

# The two screens the game shows while it is coming up, and a second way of
# seeing Home. All three are matched against real pixels here, because the only
# thing that can go wrong with a template is that the game stops looking like
# it - and that is exactly what happened to the first Home crop: an event
# decorated the bottom-nav Home tab, the crop fell to 0.56-0.78 against a
# threshold of 0.86, and every unrecognised Home frame went to the blind
# fallback. Eleven corner taps later the click guard restarted the game, which
# is why turnovers on 24 Sep cost two to four restarts each.
print("\nthe game coming up, against real pixels")
from bot.recog.image_matcher import image_match
from uma_it.asset.template import UI_GAME_LOADING, UI_GAME_TITLE, UI_MAIN_MENU_2

# Each fixture is the search region of one template, cut from a real frame.
# For the positive check it is pasted back where it came from, so the match
# runs through the template's own region config as it does on the game. For the
# negative check the template is correlated against the other regions directly:
# a template that matches another of these would have the bot act on the wrong
# screen at the one moment it has no idea where it is.
import threading as _threading
from bot.engine.executor import Executor as _Executor
from uma_it.asset.ui import GAME_LOADING as _GL, GAME_TITLE as _GT, MAIN_MENU as _HOME


class _Lock:
    detect_ui_results_write_lock = _threading.Lock()


_SCREEN = {'GAME_LOADING': _GL, 'GAME_TITLE': _GT}
_FIX = {'game_loading_region': (380, 1180, UI_GAME_LOADING),
        'game_title_region':   (40, 820,   UI_GAME_TITLE),
}
_regions = {}
for _name in _FIX:
    _regions[_name] = cv2.imread(f'resource/uma_it/fixture/{_name}.png', 0)
    check(f"the {_name} fixture loads", _regions[_name] is not None)

for _name, (_x, _y, _tpl) in _FIX.items():
    _img = _regions[_name]
    if _img is None:
        continue
    _frame = np.zeros((1280, 720), np.uint8)
    _frame[_y:_y + _img.shape[0], _x:_x + _img.shape[1]] = _img
    # Through the executor's own matcher, not image_match directly. The first
    # version of this check called image_match and passed, while the executor
    # - which crops to a template's region before image_match crops again -
    # could not see these screens at all. Test the path the bot runs.
    _found = []
    _Executor.detect_ui_sub(_Lock(), _SCREEN[_tpl.template_name], _frame, _found)
    check(f"{_tpl.template_name} is detected by the executor on its own screen",
          [u.ui_name for u in _found] == [_SCREEN[_tpl.template_name].ui_name],
          str([u.ui_name for u in _found]))
    for _other, _oimg in _regions.items():
        if _other == _name or _oimg is None:
            continue
        _t = _tpl.template_image
        if _oimg.shape[0] < _t.shape[0] or _oimg.shape[1] < _t.shape[1]:
            continue
        _score = float(cv2.matchTemplate(_oimg, _t, cv2.TM_CCOEFF_NORMED).max())
        check(f"  and scores under the threshold on {_other}", _score < 0.86,
              f"{_score:.3f}")

# Home is the nav bar minus the screens that share it. Built from two real
# fixtures: the nav bar off a Home frame, and Support Formation's title label.
print("\nHome versus a setup screen, through the executor")
_nav = cv2.imread('resource/uma_it/fixture/home_nav_region.png', 0)
_sup = cv2.imread('resource/uma_it/fixture/support_title_region.png', 0)
check("the Home fixtures load", _nav is not None and _sup is not None)
if _nav is not None and _sup is not None:
    _frame = np.zeros((1280, 720), np.uint8)
    _frame[1160:1280, 500:720] = _nav
    _found = []
    _Executor.detect_ui_sub(_Lock(), _HOME, _frame, _found)
    check("the nav bar alone is Home", _found == [_HOME], str([u.ui_name for u in _found]))
    _frame[150:200, 0:260] = _sup
    _found = []
    _Executor.detect_ui_sub(_Lock(), _HOME, _frame, _found)
    check("  the same nav bar under Support Formation's title is not",
          _found == [], str([u.ui_name for u in _found]))

print("\nthe loading screen, which must click nothing")
# It is static for up to three and a half minutes. A tap per frame reaches the
# click guard in twelve seconds, and the guard restarts the game - back to this
# same screen.
ctx = FakeCtx()
for _ in range(5):
    enter.script_game_loading(ctx)
check("nothing is clicked while the game loads", ctx.ctrl.clicks == [],
      str(ctx.ctrl.clicks))
check("  and it says so once, not once a frame",
      ctx.career.loading_logged is True)

print("\nthe title screen, which must tap but not forever")
ctx = FakeCtx()
for _ in range(enter.MAX_TITLE_TAPS + 4):
    enter.script_game_title(ctx)
check("it taps to start", ctx.ctrl.clicks and ctx.ctrl.clicks[0] == NAME(TITLE_TAP),
      str(ctx.ctrl.clicks[:1]))
check("  a bounded number of times, short of the guard's eleven",
      len(ctx.ctrl.clicks) == enter.MAX_TITLE_TAPS < 11, str(len(ctx.ctrl.clicks)))

# 25 Sep: out of daily legacy borrows. With use_last_parents the remembered
# parent was a borrowed one, so the game left its slot reading "Select a
# Legacy" and locked Next. The handler pressed the locked Next until the click
# guard restarted the game, which came back to the same screen, for over an
# hour. Nothing can start until the borrows reset, so the task stops.
print("\nLegacy Select, out of daily borrows")
_band = cv2.imread('resource/uma_it/fixture/legacy_empty_slot_band.png', 0)
check("the empty-slot fixture loads", _band is not None)
if _band is not None:
    _frame = np.zeros((1280, 720), np.uint8)
    _frame[740:860, :] = _band
    check("an empty slot is read off the real frame", enter.legacy_slot_empty(_frame))
    _frame[740:860, 160:345] = 0             # blank the empty slot's text
    check("  and a frame without that text is not", not enter.legacy_slot_empty(_frame))

from uma_it.task import EndTaskReason as _ItReason
real_empty = enter.legacy_slot_empty
try:
    enter.legacy_slot_empty = lambda _img: True
    ctx = FakeCtx(use_last_parents=True)
    ended = []
    ctx.task.end_task = lambda status, reason: ended.append(reason)
    enter.script_extend_umamusume_select(ctx)
    check("one frame of an empty slot only looks again",
          ended == [] and ctx.ctrl.clicks == [], str((ended, ctx.ctrl.clicks)))
    enter.script_extend_umamusume_select(ctx)
    check("  a second stops the task, as out of legacy borrows",
          ended == [_ItReason.NO_LEGACY_BORROWS], str(ended))
    check("  without ever pressing the locked Next", ctx.ctrl.clicks == [],
          str(ctx.ctrl.clicks))

    # The auto-select flow fills empty slots itself, so without
    # use_last_parents an empty slot is where it starts, not a dead end.
    ctx = FakeCtx(use_last_parents=False)
    ended = []
    ctx.task.end_task = lambda status, reason: ended.append(reason)
    enter.script_extend_umamusume_select(ctx)
    enter.script_extend_umamusume_select(ctx)
    check("without use_last_parents an empty slot is left to auto-select",
          ended == [] and NAME(TO_CULTIVATE_PREPARE_AUTO_SELECT) in ctx.ctrl.clicks,
          str((ended, ctx.ctrl.clicks[:1])))

    enter.legacy_slot_empty = lambda _img: False
    ctx = FakeCtx(use_last_parents=True)
    ctx.career.legacy_empty_seen = 1         # a stale count from a passing frame
    enter.script_extend_umamusume_select(ctx)
    check("both slots filled presses Next as before",
          ctx.ctrl.clicks == [NAME(TO_CULTIVATE_PREPARE_NEXT)], str(ctx.ctrl.clicks))
    check("  and forgets the passing empty frame", ctx.career.legacy_empty_seen == 0)
finally:
    enter.legacy_slot_empty = real_empty

print("\nHome, with the search stubbed")
enter.find_green_button = lambda *_a: (543, 1112)
ctx = FakeCtx()
enter.script_main_menu(ctx)
check("clicks CAREER where the colour search found it",
      ctx.ctrl.clicks == [(543, 1112, "CAREER (found by colour)")], str(ctx.ctrl.clicks))
check("  under a name that distinguishes it from the fallback",
      "colour" in ctx.ctrl.clicks[0][2])

# A miss is normally the screen mid-transition after CAREER was already
# pressed, so falling back immediately means a second, redundant tap on Home.
# That is what the parent does, and it is why its logs show a warning two
# seconds after a successful press.
enter.find_green_button = lambda *_a: None
enter.describe_green_candidates = lambda *_a, **_k: "mask empty"
ctx = FakeCtx()
for i in range(enter.CAREER_MISSES_BEFORE_FALLBACK):
    enter.script_main_menu(ctx)
check("the first misses wait rather than clicking", ctx.ctrl.clicks == [],
      str(ctx.ctrl.clicks))
check("  and are counted",
      ctx.career.career_button_misses == enter.CAREER_MISSES_BEFORE_FALLBACK,
      str(ctx.career.career_button_misses))

enter.script_main_menu(ctx)
check("falls back to the fixed point once the misses persist",
      ctx.ctrl.clicks == [NAME(TO_CULTIVATE_SCENARIO_CHOOSE)], str(ctx.ctrl.clicks))
check("  and resets the counter", ctx.career.career_button_misses == 0,
      str(ctx.career.career_button_misses))

# A success after a miss must clear the count, or a run of unlucky frames
# spread across a career would eventually trip the fallback for no reason.
enter.find_green_button = lambda *_a: (543, 1112)
ctx = FakeCtx(career_state={'career_button_misses': 2})
enter.script_main_menu(ctx)
check("a success clears earlier misses", ctx.career.career_button_misses == 0,
      str(ctx.career.career_button_misses))

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
