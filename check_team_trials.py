"""Team trials in the gaps: what gets clicked, and when it stops.

The session runs on the Race tab, where the career handlers' click points mean
other things, so the two assertions that matter are that it claims every frame
while it is live, and that it ends - on the game saying there is no RP, on a
screen it cannot name, or on the clock.
"""
import os, sys, time
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

import numpy as np

import uma_it.team_trials as tt
import uma_it.dialogs as dialogs
from uma_it.asset import point as P
from uma_it.asset import template as T
from uma_it.context import CareerContext
from uma_it.task import build_task, EndTaskReason
from bot.base.task import TaskExecuteMode, TaskStatus

tt.time.sleep = lambda *_: None
dialogs.time.sleep = lambda *_: None
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

    def click_by_point(self, p):
        self.clicks.append(NAME(p))

    def click(self, x, y, name):
        self.clicks.append((x, y, name))


class FakeCtx:
    def __init__(self, **settings):
        self.ctrl = FakeCtrl()
        self.career = CareerContext()
        self.current_screen = np.zeros((1280, 720, 3), np.uint8)
        self.task = build_task(TaskExecuteMode.TASK_EXECUTE_MODE_LOOP, 1, "tt", None,
                               dict({'tt_pending': True}, **settings))
        self.ended = []
        self.task.end_task = lambda s, r: self.ended.append((s, r))


class Found:
    def __init__(self, hit, centre=(300, 900)):
        self.find_match = hit
        self.center_point = centre


def only(template):
    """Let exactly one template match, the way one screen would."""
    tt.image_match = lambda _img, t: Found(t is template)


print("the session runs only when the task owes one")
ctx = FakeCtx()
check("tt_pending means a session is owed", tt.active(ctx) is True)
ctx.task.detail.tt_pending = False
check("  and without it nothing runs", tt.active(ctx) is False)
check("the setting is off unless asked for",
      tt.wanted(FakeCtx()) is False)
check("  and on when the task asks",
      tt.wanted(FakeCtx(team_trials_while_waiting=True)) is True)

print("\neach screen clicks its own point")
for template, expected in [
    (T.REF_TT_HOME, P.TT_RACE_TAB),
    (T.REF_TT_TEAM_TRIALS, P.TT_TEAM_TRIALS),
    (T.REF_TT_TEAM_RACE, P.TT_TEAM_RACE),
    (T.REF_TT_SELECT_OPPONENT, P.TT_SELECT_OPPONENT),
    (T.REF_TT_SEE_ALL, P.TT_SEE_ALL),
    (T.REF_TT_SEE_RESULTS, P.TT_SEE_RESULTS),
    (T.REF_TT_NEXT_RESULT, P.TT_NEXT_RESULT),
]:
    ctx = FakeCtx()
    only(template)
    claimed = tt.run_frame(ctx)
    check(f"{NAME(expected)}", claimed and ctx.ctrl.clicks == [NAME(expected)],
          str(ctx.ctrl.clicks))

# The results Next moves with its screen, so it is clicked where it was found.
ctx = FakeCtx()
only(T.REF_NEXT)
tt.run_frame(ctx)
check("the results Next is clicked where it was found, then confirmed",
      ctx.ctrl.clicks == [(300, 900, "Team trials - Next"), NAME(P.TT_NEXT_AFTER)],
      str(ctx.ctrl.clicks))

# The countdown screen has no Back button: its menu holds "To Home" and, three
# hundred pixels to the right, "Give Up", which abandons the career. So this
# one is matched and clicked where it was found, never at a fixed point.
ctx = FakeCtx()
only(T.REF_TT_TO_HOME)
tt.run_frame(ctx)
check("To Home is clicked where it was found, not at a coordinate",
      ctx.ctrl.clicks == [(300, 900, "Team trials - To Home")], str(ctx.ctrl.clicks))

ctx = FakeCtx(team_trials_while_waiting=True)
ctx.task.detail.tt_pending = False
tt.begin_in_career(ctx)
tt.image_match = lambda _img, _t: Found(False)
tt.run_frame(ctx)
ctx.career.tt_last_action_at = time.time() - tt.BACK_OUT_AFTER_SECONDS - 1
tt.run_frame(ctx)
check("a session inside a career opens the training menu instead of Back",
      ctx.ctrl.clicks == [NAME(P.IT_MENU)], str(ctx.ctrl.clicks))

# Measured 19 Sep: the parent's "no RP" crop never matched on this version of
# the game. What actually appears is a Confirm dialog offering to restore RP,
# and the session sat on it until the quiet limit.
print("\nthe game's own words are what end a session")
check("the RP prompt is told from the TP one",
      tt.is_rp_prompt("Not enough RP. Do you want to restore RP?") is True
      and tt.is_rp_prompt("You need 2 more TP to start a Career Scenario") is False,
      str((tt.is_rp_prompt("Not enough RP. Do you want to restore RP?"),
           tt.is_rp_prompt("You need 2 more TP to start a Career Scenario"))))

ctx = FakeCtx()
tt.image_match = lambda _img, _t: Found(False)
real_title, real_ocr = tt._read_title, tt.ocr_line
tt._read_title = lambda _ctx, _img: 'Confirm'
tt.ocr_line = lambda _crop: "Not enough RP. Do you want to restore RP?"
tt.run_frame(ctx)
check("it declines the restore", ctx.ctrl.clicks == [NAME(P.RESTORE_NO)],
      str(ctx.ctrl.clicks))
check("  and the session is on its way home",
      ctx.career.tt_returning is True, str(ctx.career.tt_returning))
check("  recording when RP ran out", ctx.task.detail.tt_last_empty_at > 0,
      str(ctx.task.detail.tt_last_empty_at))
# Put the real readers back: with every frame reading as an RP prompt, the
# checks below would be testing this patch rather than the flow.
tt._read_title, tt.ocr_line = real_title, real_ocr

# ... and with no session running, the dialog router must not read it as TP:
# that is what held the loop for half an hour with a career still going.
ctx = FakeCtx()
ctx.task.detail.tt_pending = False
dialogs.read_title = lambda _ctx: 'Confirm'
dialogs.read_body = lambda _ctx, _hdr: "Not enough RP. Do you want to restore RP?"
dialogs.script_dialog(ctx)
check("the router declines an RP prompt without waiting for TP",
      ctx.ctrl.clicks == [NAME(P.RESTORE_NO)], str(ctx.ctrl.clicks))
check("  and does not end the run", ctx.ended == [], str(ctx.ended))
check("  nor hold the loop", (ctx.task.detail.resume_after or 0) == 0,
      str(ctx.task.detail.resume_after))

dialogs.read_body = lambda _ctx, _hdr: "You need 2 more TP to start a Career Scenario."
ctx = FakeCtx()
ctx.task.detail.tt_pending = False
dialogs.script_dialog(ctx)
check("  while a TP prompt still holds the loop",
      ctx.task.detail.resume_after > int(time.time()), str(ctx.task.detail.resume_after))

print("\nout of RP ends the session, which is the expected end")
for template in (T.REF_TT_CANT, T.REF_TT_CANT_2):
    ctx = FakeCtx()
    only(template)
    tt.run_frame(ctx)
    check("it leaves the screen", ctx.ctrl.clicks == [NAME(P.TT_DONE), NAME(P.TT_DONE)],
          str(ctx.ctrl.clicks))
    # Not over yet: the session ends on Home, never on a Race tab screen.
    check("  and starts walking back to Home", ctx.career.tt_returning is True)
    check("  without ending the run there", ctx.ended == [], str(ctx.ended))
    only(T.REF_TT_HOME)
    tt.run_frame(ctx)
    check("  the run ends once Home is on screen",
          [r for _, r in ctx.ended] == [EndTaskReason.TEAM_TRIALS_DONE], str(ctx.ended))
    check("  and it stops owing a session", ctx.task.detail.tt_pending is False)

# Handing the frames back on a Race tab screen is what cost five hours on
# 19 Sep: nothing there has a template, so the blind fallback clicked a corner
# every second, the click guard restarted the game, and the game came back to
# the same screen. The bot only got out when the daily reset dialog appeared.
print("\nthe session ends on Home, not wherever it happens to finish")
ctx = FakeCtx()
only(T.REF_TT_CANT)
tt.run_frame(ctx)                       # out of RP -> returning
tt.image_match = lambda _img, _t: Found(False)
ctx.ctrl.clicks.clear()
tt.run_frame(ctx)
check("it presses Home while nothing is recognised",
      ctx.ctrl.clicks == [NAME(P.HOME_TAB)], str(ctx.ctrl.clicks))
check("  and keeps claiming the frames", tt.active(ctx) is True)
for _ in range(tt.MAX_RETURN_CLICKS + 3):
    tt.run_frame(ctx)
check("  but gives up rather than pressing forever",
      len(ctx.ctrl.clicks) == tt.MAX_RETURN_CLICKS, str(len(ctx.ctrl.clicks)))
check("  handing back anyway", tt.active(ctx) is False and ctx.career.tt_returning is False)

# Out-of-RP is checked before anything that would start another race: the game
# shows both on the same frame, and paying for a race it cannot afford leaves
# the flow somewhere nobody has studied.
order = [t for _, t, _ in tt.RULES]
check("out of RP is matched before the race buttons",
      order.index(T.REF_TT_CANT) == 0 and order.index(T.REF_TT_TEAM_RACE) > 1,
      str([n for n, _, _ in tt.RULES][:4]))

print("\nevery frame is claimed, matched or not")
# The career handlers must never act on these screens - the bot is on the Race
# tab, where their points mean other things.
ctx = FakeCtx()
tt.image_match = lambda _img, _t: Found(False)
check("an unrecognised frame is still claimed", tt.run_frame(ctx) is True)
check("  and nothing is clicked on it", ctx.ctrl.clicks == [], str(ctx.ctrl.clicks))
check("  and the session continues", ctx.ended == [], str(ctx.ended))

print("\na session starts where the TP prompt left the bot, not on Home")
ctx = FakeCtx()
tt.image_match = lambda _img, _t: Found(False)
tt.run_frame(ctx)
ctx.career.tt_last_action_at = time.time() - tt.BACK_OUT_AFTER_SECONDS - 1
tt.run_frame(ctx)
check("it backs out towards Home", ctx.ctrl.clicks == [NAME(P.TT_BACK)],
      str(ctx.ctrl.clicks))
for _ in range(tt.MAX_BACK_CLICKS + 2):
    ctx.career.tt_last_action_at = time.time() - tt.BACK_OUT_AFTER_SECONDS - 1
    tt.run_frame(ctx)
check("  a bounded number of times, not forever",
      len(ctx.ctrl.clicks) == tt.MAX_BACK_CLICKS, str(len(ctx.ctrl.clicks)))

# Backing out of a race would lose it, so Back stops once the flow is moving.
ctx = FakeCtx()
only(T.REF_TT_TEAM_RACE)
tt.run_frame(ctx)
tt.image_match = lambda _img, _t: Found(False)
ctx.career.tt_last_action_at = time.time() - tt.BACK_OUT_AFTER_SECONDS - 1
tt.run_frame(ctx)
check("and never once the flow is past Home",
      ctx.ctrl.clicks == [NAME(P.TT_TEAM_RACE)], str(ctx.ctrl.clicks))

print("\nand a session that stops making sense ends rather than clicking on")
ctx = FakeCtx()
tt.image_match = lambda _img, _t: Found(False)
tt.run_frame(ctx)
# Past Home, so backing out is no longer an option: this is the flow stuck on
# a screen the rules do not name, which is what the quiet limit is for.
ctx.career.tt_raced = True
ctx.career.tt_last_action_at = time.time() - tt.QUIET_LIMIT_SECONDS - 1
tt.run_frame(ctx)
check("quiet for longer than a race ends it", ctx.career.tt_returning is True,
      str(ctx.career.tt_returning))
check("  having clicked nothing", ctx.ctrl.clicks == [], str(ctx.ctrl.clicks))
only(T.REF_TT_HOME)
tt.run_frame(ctx)
check("  and the run ends back on Home",
      [r for _, r in ctx.ended] == [EndTaskReason.TEAM_TRIALS_DONE], str(ctx.ended))

ctx = FakeCtx()
tt.image_match = lambda _img, _t: Found(False)
tt.run_frame(ctx)
ctx.career.tt_started_at = time.time() - tt.SESSION_LIMIT_SECONDS - 1
ctx.career.tt_last_action_at = time.time()
tt.run_frame(ctx)
check("a session that runs long ends too", ctx.career.tt_returning is True,
      str(ctx.career.tt_returning))
only(T.REF_TT_HOME)
tt.run_frame(ctx)
check("  once it is back on Home",
      [r for _, r in ctx.ended] == [EndTaskReason.TEAM_TRIALS_DONE], str(ctx.ended))

print("\nthe career countdown is the cheapest RP in the loop")
# Fifty of a career's fifty-two minutes are a countdown the game runs without
# the bot, while RP builds up at a point every ninety minutes and caps at 5.
import uma_it.career as career_mod
career_mod.time.sleep = lambda *_: None

ctx = FakeCtx(team_trials_while_waiting=True)
ctx.task.detail.tt_pending = False
check("a session is due when RP has had time to come back", tt.due(ctx) is True)
ctx.task.detail.tt_last_empty_at = int(time.time())
check("  and not right after one ran RP to zero", tt.due(ctx) is False)
ctx.task.detail.tt_last_empty_at = int(time.time()) - tt.RP_RETRY_SECONDS - 1
check("  and again once RP has rebuilt", tt.due(ctx) is True)
check("  never when the task did not ask", tt.due(FakeCtx()) is False)


def wait_frame(remaining, **settings):
    ctx = FakeCtx(**settings)
    ctx.task.detail.tt_pending = False
    career_mod.ocr_line = lambda _img: remaining
    career_mod.script_wait(ctx)
    return ctx


ctx = wait_frame("0:49:30 left", team_trials_while_waiting=True)
check("the countdown hands over to a session", ctx.career.tt_active is True)
check("  without clicking anything, as that handler must not",
      ctx.ctrl.clicks == [], str(ctx.ctrl.clicks))
check("  and a session in a career claims frames",
      tt.active(ctx) is True)

ctx = wait_frame("0:03:10 left", team_trials_while_waiting=True)
check("a career nearly done is left alone", ctx.career.tt_active is False)
ctx = wait_frame("", team_trials_while_waiting=True)
check("  and so is a countdown that could not be read",
      ctx.career.tt_active is False)
ctx = wait_frame("0:49:30 left")
check("  and nothing happens when the task did not ask",
      ctx.career.tt_active is False)

check("the countdown is read in minutes",
      (career_mod.minutes_left("0:49:30 left"), career_mod.minutes_left("1:02:00"),
       career_mod.minutes_left("")) == (49, 62, None),
      str((career_mod.minutes_left("0:49:30 left"), career_mod.minutes_left("1:02:00"),
           career_mod.minutes_left(""))))

print("\na session inside a career goes back to the career, not the loop")
ctx = FakeCtx(team_trials_while_waiting=True)
ctx.task.detail.tt_pending = False
tt.begin_in_career(ctx)
only(T.REF_TT_CANT)
tt.run_frame(ctx)
check("out of RP leaves the Race tab", ctx.ctrl.clicks == [NAME(P.TT_DONE), NAME(P.TT_DONE)],
      str(ctx.ctrl.clicks))
only(T.REF_TT_HOME)
tt.run_frame(ctx)
check("  the run is not ended - the career is still going", ctx.ended == [], str(ctx.ended))
check("  the session is over", ctx.career.tt_active is False and tt.active(ctx) is False)
check("  and RP is not asked about again straight away", tt.due(ctx) is False)

print("\na TP wait is what schedules a session")
dialogs_ctx = FakeCtx(team_trials_while_waiting=True)
dialogs_ctx.task.detail.tt_pending = False
dialogs._wait_for_tp(dialogs_ctx, "You need 2 more TP to start a Career Scenario.", "test")
check("the wait asks for a session when the task wants one",
      dialogs_ctx.task.detail.tt_pending is True)
# The prompt is modal. Left up it blocks the very session the wait just asked
# for: on 19 Sep the bot sat behind one with three RP unspent, looking asleep.
check("  and the prompt is dismissed, not left on screen",
      NAME(P.RESTORE_NO) in dialogs_ctx.ctrl.clicks, str(dialogs_ctx.ctrl.clicks))

# ... but not one that would walk to the Race tab to be told RP is empty,
# which is what happened at 07:34 on 19 Sep, minutes after a session.
spent = FakeCtx(team_trials_while_waiting=True)
spent.task.detail.tt_pending = False
spent.task.detail.tt_last_empty_at = int(time.time())
dialogs._wait_for_tp(spent, "You need 2 more TP to start a Career Scenario.", "test")
check("  and none when RP was just emptied",
      spent.task.detail.tt_pending is False)
check("  though it still waits for the TP",
      spent.task.detail.resume_after > int(time.time()))
check("  and still sets the wait itself",
      dialogs_ctx.task.detail.resume_after > int(time.time()),
      str(dialogs_ctx.task.detail.resume_after))

off = FakeCtx()
off.task.detail.tt_pending = False
dialogs._wait_for_tp(off, "You need 2 more TP to start a Career Scenario.", "test")
check("  and asks for nothing when the task does not want it",
      off.task.detail.tt_pending is False)

print("\nthe scheduler starts the task for a session, wait or no wait")
from bot.base.purge import serialize_umamusume_task
from bot.engine.scheduler import scheduler as sched


class FakeExecutor:
    active = False

    def __init__(self):
        self.started = []

    def start(self, *tasks):
        self.started.append(tasks)


task = build_task(TaskExecuteMode.TASK_EXECUTE_MODE_LOOP, 1, "tt", None,
                  {'loop_count': 0, 'team_trials_while_waiting': True,
                   'tt_pending': True})
task.task_status = TaskStatus.TASK_STATUS_PENDING
task.detail.resume_after = int(time.time()) + 900
sched.task_list = [task]
sched.active = True
sched.stop_after_run = False
fe = FakeExecutor()
sched.tick(fe)
time.sleep(0.3)
check("a pending session runs during the wait", len(fe.started) == 1, str(fe.started))

task.detail.tt_pending = False
fe2 = FakeExecutor()
sched.tick(fe2)
time.sleep(0.3)
check("  and once it is done the wait holds again", fe2.started == [], str(fe2.started))
sched.active = False
sched.task_list = []

print("\nthe settings survive the restart")
saved = build_task(TaskExecuteMode.TASK_EXECUTE_MODE_LOOP, 1, "tt", None,
                   {'team_trials_while_waiting': True, 'tt_pending': True})
back = build_task(TaskExecuteMode.TASK_EXECUTE_MODE_LOOP, 1, "tt", None,
                  serialize_umamusume_task(saved) or {})
check("the setting comes back", back.detail.team_trials_while_waiting is True)
check("  and so does an owed session", back.detail.tt_pending is True)
older = build_task(TaskExecuteMode.TASK_EXECUTE_MODE_LOOP, 1, "tt", None, {})
check("a task saved before the feature restores with it off",
      older.detail.team_trials_while_waiting is False and older.detail.tt_pending is False)

print(f"\n{len(failures)} failed")
sys.exit(1 if failures else 0)
