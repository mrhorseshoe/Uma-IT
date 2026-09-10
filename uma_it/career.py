"""The run itself: waiting it out, and closing the log when it ends.

These two screens are where a career spends nearly all of its wall-clock time.
Fifty of a career's fifty-two minutes are the countdown, and the job there is
to do nothing correctly, which is harder than it sounds.
"""
import time

from bot.recog.ocr import ocr_line
import bot.base.log as logger

from uma_it.asset.point import INDEPENDENT_TRAINING_RESULTS_OK

log = logger.get_logger(__name__)

# Where the countdown sits on the Independent Training screen, at 720x1280.
COUNTDOWN_REGION = (1098, 1135, 300, 520)   # y1, y2, x1, x2

# How long to wait between passes. The countdown changes by the second and the
# run lasts about fifty minutes, so polling every executor tick would mean
# three thousand screenshots to watch a number tick down.
POLL_SECONDS = 10


def script_wait(ctx):
    """The countdown screen. **This handler must not click.**

    That is the whole reason it exists. Without an entry of its own the frame
    falls to `NOT_FOUND_UI`, which blind-clicks a corner under a fixed name,
    and eleven identical consecutive clicks trip the engine's repetitive-click
    guard into restarting the app. The executor dispatches roughly once a
    second, so a screen the bot sits on for fifty minutes would trip that guard
    within about a dozen ticks and then keep tripping it.

    On the freeze watchdog, which restarts the game when the downscaled frame
    stops changing: this screen is **not** marginal, and the note that it might
    be was wrong. Measured, it scores about 55x the threshold of 1.0 - the
    ticking countdown and the uma animation keep it well clear. When the
    watchdog does fire here, the score does not drift down to the line; it
    drops to exactly 0.000 between one sample and the next, while the in-game
    clock keeps perfect wall-clock time across the stall. The game is fine and
    the capture is not. **Raising the threshold cannot help** - 0.000 trips any
    positive threshold - so if this screen ever needs attention, the question
    is ADB, uiautomator2 or the emulator's screencap, not this handler.
    """
    career = getattr(ctx, 'career', None)

    remaining = ''
    try:
        y1, y2, x1, x2 = COUNTDOWN_REGION
        remaining = (ocr_line(ctx.current_screen[y1:y2, x1:x2]) or '').strip()
    except Exception:
        # A missed read costs one log line. It must never cost a click.
        pass

    # Feed the status panel, which shows the countdown live.
    try:
        from bot.base.runtime_state import update_independent_training
        update_independent_training(remaining)
    except Exception:
        pass

    # Log on the minute rather than every pass: at one line per ten seconds
    # this screen alone would be three hundred lines a career.
    minute = remaining.rsplit(':', 1)[0] if ':' in remaining else remaining
    if minute and career is not None and minute != career.last_countdown_log:
        log.info(f"Independent Training in progress - {remaining}")
        career.last_countdown_log = minute

    time.sleep(POLL_SECONDS)


def script_results(ctx):
    """The Training Log a finished run parks on, which has to be dismissed.

    The game waits here indefinitely. Dismissing it leads to the ordinary
    end-of-career flow - results, ratings, and optionally skills and sparks -
    so this handler's only job is the one click.
    """
    log.info("Independent Training finished - closing the training log")
    career = getattr(ctx, 'career', None)
    if career is not None:
        # The next run starts a fresh countdown; do not suppress its first
        # log line because it happens to share a minute with this one's last.
        career.last_countdown_log = ''
    ctx.ctrl.click_by_point(INDEPENDENT_TRAINING_RESULTS_OK)
    time.sleep(1)
