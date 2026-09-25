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

# The results Next moves with its screen, so it is clicked where it was found -
# once the session is inside its own flow, which the opponent list proves.
ctx = FakeCtx()
only(T.REF_TT_SELECT_OPPONENT)
tt.run_frame(ctx)
ctx.ctrl.clicks.clear()
only(T.REF_NEXT)
tt.run_frame(ctx)
check("the results Next is clicked where it was found, then confirmed",
      ctx.ctrl.clicks == [(300, 900, "Team trials - Next"), NAME(P.TT_NEXT_AFTER)],
      str(ctx.ctrl.clicks))

# 25 Sep, 16:48: a session that began on Support Formation matched the generic
# Next button there and pressed it into the career setup. The match also
# switched off the Back budget, so it had no way out, and the watchdog
# restarted the game. Before the session has seen a screen that exists only in
# team trials, a Next button is none of its business.
ctx = FakeCtx()
only(T.REF_NEXT)
tt.run_frame(ctx)
check("a Next button before the session reaches team trials is not pressed",
      ctx.ctrl.clicks == [], str(ctx.ctrl.clicks))
check("  and does not use up the way back", ctx.career.tt_raced is False)
ctx.career.tt_last_action_at = time.time() - tt.BACK_OUT_AFTER_SECONDS - 1
tt.run_frame(ctx)
check("  so the session backs out towards Home instead",
      ctx.ctrl.clicks == [NAME(P.TT_BACK)], str(ctx.ctrl.clicks))

# Home is not team trials - every setup screen is reached from it - so seeing
# Home alone does not open the Next rule either.
ctx = FakeCtx()
only(T.REF_TT_HOME)
tt.run_frame(ctx)
check("Home does not count as being in the flow", ctx.career.tt_in_flow is False)
only(T.REF_TT_TEAM_TRIALS)
tt.run_frame(ctx)
check("  the Race tab does", ctx.career.tt_in_flow is True)

# A session begins wherever the loop was standing still - Home, or the career
# start screens a declined TP prompt left the bot on. Back walks out of both,
# and it is bounded: one point clicked over and over is what the repetitive
# click guard restarts the game over.
ctx = FakeCtx(team_trials_while_waiting=True)
tt.image_match = lambda _img, _t: Found(False)
tt.run_frame(ctx)
ctx.career.tt_last_action_at = time.time() - tt.BACK_OUT_AFTER_SECONDS - 1
tt.run_frame(ctx)
check("a session that is not on Home yet backs out towards it",
      ctx.ctrl.clicks == [NAME(P.TT_BACK)], str(ctx.ctrl.clicks))

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

# 20 Sep: the shop's Daily Sale offer appeared mid-session. No rule matched it,
# and a session that recognises nothing clicks nothing - so the screen sat
# still until the 30s watchdog reached three strikes and restarted the game,
# ninety seconds before the session's own quiet limit would have ended it. The
# session has to clear this one itself; the router never sees it.
print("\nthe Daily Sale offer is cleared by the session, not waited out")
ctx = FakeCtx()
tt.image_match = lambda _img, _t: Found(False)
real_title = tt._read_title
try:
    tt._read_title = lambda _ctx, _img: 'Daily Sale'
    import uma_it.dialogs as dialogs_mod
    green = dialogs_mod.find_green_button
    try:
        dialogs_mod.find_green_button = lambda *_a: (498, 906)
        tt.run_frame(ctx)
    finally:
        dialogs_mod.find_green_button = green
    check("it cancels rather than sitting through it",
          ctx.ctrl.clicks == [(222, 906, "Daily Sale - Cancel")], str(ctx.ctrl.clicks))
    check("  and the session stays alive", ctx.ended == [], str(ctx.ended))
finally:
    tt._read_title = real_title

# 25 Sep, the daily reset: the session reached the Race tab at 11:00:08,
# something came up over it, and nothing handled it - the session claims every
# frame, so the dialog router never saw it. The watchdog restarted the game two
# minutes later and the session then sat on the title screen until its quiet
# limit. Six minutes lost, nothing logged, nothing photographed.
print("\nthe daily reset during a session")
import uma_it.dialogs as dialogs_rt
from uma_it.asset.point import ESCAPE as _ESCAPE
dialogs_rt.time.sleep = lambda *_: None
real_title, real_capture = tt._read_title, dialogs_rt._capture_unknown
photographed = []
dialogs_rt._capture_unknown = lambda _ctx, raw: photographed.append(raw)
try:
    tt.image_match = lambda _img, _t: Found(False)

    tt._read_title = lambda _ctx, _img: 'Date Changed'
    ctx = FakeCtx(team_trials_while_waiting=True)
    claimed = tt.run_frame(ctx)
    check("'Date Changed' is handed to the router and confirmed",
          claimed is True and ctx.ctrl.clicks == [(383, 840, "Date Changed - confirming")],
          str(ctx.ctrl.clicks))
    check("  and the session carries on", ctx.ended == [] and tt.active(ctx) is True)

    tt._read_title = lambda _ctx, _img: 'Network Error'
    ctx = FakeCtx(team_trials_while_waiting=True)
    tt.run_frame(ctx)
    check("so is a network error", len(ctx.ctrl.clicks) == 1, str(ctx.ctrl.clicks))

    tt._read_title = lambda _ctx, _img: 'Some Dialog Nobody Has Seen'
    ctx = FakeCtx(team_trials_while_waiting=True)
    tt.run_frame(ctx)
    check("a dialog nobody knows is photographed",
          photographed == ['Some Dialog Nobody Has Seen'], str(photographed))
    check("  and cleared the way the router clears unknowns",
          ctx.ctrl.clicks == [NAME(_ESCAPE)], str(ctx.ctrl.clicks))

    # Career dialogs mean nothing on the Race tab, and their click points are
    # someone else's buttons there.
    for title in ('Complete Career', 'Final Confirmation', 'Overwrite'):
        tt._read_title = lambda _ctx, _img, _t=title: _t
        ctx = FakeCtx(team_trials_while_waiting=True)
        tt.run_frame(ctx)
        check(f"a career dialog ({title!r}) is left alone", ctx.ctrl.clicks == [],
              str(ctx.ctrl.clicks))
finally:
    tt._read_title, dialogs_rt._capture_unknown = real_title, real_capture

# The watchdog's restart lands on the loading and title screens, which the
# session cannot drive - the title needs a tap a session never gives.
for screen in (T.UI_GAME_LOADING, T.UI_GAME_TITLE):
    ctx = FakeCtx(team_trials_while_waiting=True)
    only(T.REF_TT_HOME)
    tt.run_frame(ctx)                    # the session gets going
    ctx.ctrl.clicks.clear()
    only(screen)
    claimed = tt.run_frame(ctx)
    check(f"a restart under the session ({screen.template_name}) ends it at once",
          claimed is False and tt.active(ctx) is False, str((claimed, tt.active(ctx))))
    check("  clicking nothing, and leaving the run to carry on",
          ctx.ctrl.clicks == [] and ctx.ended == [], str((ctx.ctrl.clicks, ctx.ended)))

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
    # Stop where the manifest stops: it only calls run_frame while a session is
    # owed, and the last Back click is followed by a stand-down.
    if not tt.active(ctx):
        break
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

print("\nRP is spent between careers, never inside one")
# There used to be a second path here: the countdown handler handed a running
# career over to a session, which spent its RP and walked back in. RP accrues
# at a point every ninety minutes, which is too slow for a career-length gap
# to be worth interrupting, and that path owned every sharp edge in this
# module - the way out of the countdown, the way back, and career state that
# had to survive both. What is pinned now is that the countdown does nothing.
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


for label, remaining in (("a long countdown", "0:49:30 left"),
                         ("one nearly done", "0:03:10 left"),
                         ("an unreadable one", "")):
    ctx = wait_frame(remaining, team_trials_while_waiting=True)
    check(f"{label} clicks nothing and starts nothing",
          ctx.ctrl.clicks == [] and tt.active(ctx) is False,
          str((ctx.ctrl.clicks, tt.active(ctx))))

# The run that spends the RP is a run of its own, started before the career.
# The one way a session can find itself in front of a running career: the run
# began with a career pending in-game, which is what a watchdog restart leaves
# behind. It must not interrupt it, and it could not walk out of that screen
# if it tried - the countdown has no Back and no bottom nav.
print("\na session in front of a running career stands down")
ctx = FakeCtx(team_trials_while_waiting=True)
only(T.UI_INDEPENDENT_TRAINING_WAIT)
claimed = tt.run_frame(ctx)
check("it hands the frame back rather than claiming it", claimed is False, str(claimed))
check("  clicking nothing at the career", ctx.ctrl.clicks == [], str(ctx.ctrl.clicks))
check("  and stops owing a session", ctx.task.detail.tt_pending is False)
check("  without ending the run", ctx.ended == [], str(ctx.ended))
check("  and without marking the RP spent, so the next loop tries again",
      tt.due(ctx) is True)

# 24 Sep: the loop was started while the game was still coming up. The session
# ran first, recognised nothing, spent its six Back clicks at a loading screen
# and then sat for the four-minute quiet limit - long enough for the watchdog
# to call the screen frozen and restart the game. Standing down at the end of
# the Back budget hands the frames to handlers that can get to Home.
print("\na session that cannot find anything stands down instead of sitting")
ctx = FakeCtx(team_trials_while_waiting=True)
tt.image_match = lambda _img, _t: Found(False)
claimed = True
# One extra pass: the first frame of a session sets its own clocks, so it is
# the second that can be quiet.
for _ in range(tt.MAX_BACK_CLICKS + 2):
    ctx.career.tt_last_action_at = time.time() - tt.BACK_OUT_AFTER_SECONDS - 1
    claimed = tt.run_frame(ctx)
check("it spends its Back budget first",
      ctx.ctrl.clicks == [NAME(P.TT_BACK)] * tt.MAX_BACK_CLICKS, str(len(ctx.ctrl.clicks)))
check("  then hands the frame back rather than claiming it", claimed is False, str(claimed))
check("  stops owing a session", ctx.task.detail.tt_pending is False)
check("  without ending the run", ctx.ended == [], str(ctx.ended))
check("  and keeps the RP, so the next loop tries again",
      ctx.task.detail.tt_last_empty_at == 0 and tt.due(ctx) is True,
      str(ctx.task.detail.tt_last_empty_at))

# A session that did recognise something and then got stuck is a different
# case: it may be deep in the Race tab, where handing frames back is what cost
# five hours on 19 Sep. That one still walks home and ends the run.
print("\n  while one that got going still walks home when it stalls")
ctx = FakeCtx(team_trials_while_waiting=True)
only(T.REF_TT_HOME)
tt.run_frame(ctx)
tt.image_match = lambda _img, _t: Found(False)
ctx.career.tt_last_action_at = time.time() - tt.QUIET_LIMIT_SECONDS - 1
check("it keeps claiming the frame", tt.run_frame(ctx) is True)
check("  and starts walking home", ctx.career.tt_returning is True)

print("\na session is a run of its own, started before the career")
ctx = FakeCtx(team_trials_while_waiting=True)
ctx.task.detail.tt_pending = False
ctx.task.detail.tt_last_empty_at = 0
ctx.task.start_task()
check("the loop start claims the run for a session",
      ctx.task.detail.tt_pending is True, str(ctx.task.detail.tt_pending))

ctx2 = FakeCtx(team_trials_while_waiting=True)
ctx2.task.detail.tt_pending = False
ctx2.task.detail.tt_last_empty_at = int(time.time())
ctx2.task.start_task()
check("  and starts the career when RP has not come back yet",
      ctx2.task.detail.tt_pending is False, str(ctx2.task.detail.tt_pending))

ctx3 = FakeCtx()
ctx3.task.detail.tt_pending = False
ctx3.task.detail.tt_last_empty_at = 0
ctx3.task.start_task()
check("  and never when the task did not ask for team trials",
      ctx3.task.detail.tt_pending is False, str(ctx3.task.detail.tt_pending))

# A TP wait that cleared itself here would send the bot at a career the game
# is about to refuse - and the refusal starts the wait over from the top.
ctx4 = FakeCtx(team_trials_while_waiting=True)
ctx4.task.detail.tt_pending = True
ctx4.task.detail.resume_after = int(time.time()) + 1800
ctx4.task.start_task()
check("a session does not cancel the TP wait behind it",
      ctx4.task.detail.resume_after > 0, str(ctx4.task.detail.resume_after))
ctx5 = FakeCtx(team_trials_while_waiting=True)
ctx5.task.detail.tt_pending = False
ctx5.task.detail.tt_last_empty_at = int(time.time())
ctx5.task.detail.resume_after = int(time.time()) + 1800
ctx5.task.start_task()
check("  but a career start does", ctx5.task.detail.resume_after == 0,
      str(ctx5.task.detail.resume_after))

print("\nthe session ends the run, so the career is the next one")
ctx = FakeCtx(team_trials_while_waiting=True)
only(T.REF_TT_CANT)
tt.run_frame(ctx)
check("out of RP leaves the Race tab", ctx.ctrl.clicks == [NAME(P.TT_DONE), NAME(P.TT_DONE)],
      str(ctx.ctrl.clicks))
only(T.REF_TT_HOME)
tt.run_frame(ctx)
check("  the run ends once Home is back",
      [r for _, r in ctx.ended] == [EndTaskReason.TEAM_TRIALS_DONE], str(ctx.ended))
check("  the session is no longer owed", tt.active(ctx) is False)
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
