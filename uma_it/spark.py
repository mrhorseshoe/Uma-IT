"""Spark reroll: keep the roll, or pay 30 TP for another and pick the better.

Off unless the task enables it and names at least one target. When it is on,
the end-of-career sparks screen is read, checked against the wanted sparks,
and - if none is there - rerolled. The reroll opens a carousel holding both
sets, and one of them has to be chosen.

Two things here are less obvious than they look.

**A partial read costs 30 TP.** Every uma finishes with one blue and one pink
spark at the top of the list, so a read missing either is the list still
rendering rather than a bad roll. `parse_spark_rows` re-reads before deciding;
acting on the partial read turns a satisfied roll into a miss and pays for a
reroll that was not needed.

**When neither set qualifies, the better one is chosen by scrollbar.** A set
always leads with the same three non-white rows, so more sparks means more
whites, and the thumb length reads that directly - a shorter thumb means more
rows below the fold. That beats scrolling and re-OCRing both lists, because the
in-game list flings rather than scrolling a fixed step.

Captures of every step are written to `screenshot/spark_reroll/`, which is how
these screens were calibrated in the first place.
"""
import os
import time

import cv2

import bot.base.log as logger
from bot.base.task import TaskExecuteMode, TaskStatus
from bot.recog.image_matcher import image_match
from bot.recog.ocr import ocr_line

from uma_it.asset.point import (
    CULTIVATE_FACTOR_RECEIVE_CONFIRM,
    CULTIVATE_FACTOR_REROLL_SKIP,
    ESCAPE,
)
from uma_it.asset.template import UI_FACTOR_REROLL
from uma_it.parse import (
    SPARK_SEL_CONFIRM_AREA,
    SPARK_SEL_RIGHT_ARROW,
    find_green_button,
    is_spark_selection_screen,
    parse_factor,
    parse_spark_rows,
    parse_spark_selection_title,
    read_all_spark_rows,
    spark_list_at_bottom,
    spark_rule_check,
    spark_scrollbar_ratio,
)
from uma_it import tp
from uma_it.task import EndTaskReason

log = logger.get_logger(__name__)

# `spark_scrollbar_ratio` returns exactly 1.0 when there is no scrollbar, which
# means the whole list fits one page. Measured across the 137 captured
# selection frames in `screenshot/spark_reroll/`, that sentinel and a real
# measurement separate cleanly: every frame with a scrollbar showed 9 rows (the
# page is full), every frame without showed 3-8 and never 9. So a ratio at this
# threshold is a reliable "you are seeing all of it", not a failed read.
FULLY_VISIBLE = 0.999


def _spark_reroll_active(ctx) -> bool:
    """Rerolling needs the switch and something to look for.

    Either kind of target counts. White requirements on their own are the
    whole point of the feature for parent farming, where the stats and
    aptitudes do not matter and `spark_reroll_targets` is left empty.
    """
    detail = ctx.task.detail
    return bool(getattr(detail, 'spark_reroll_enabled', False)) \
        and bool(getattr(detail, 'spark_reroll_targets', None)
                 or getattr(detail, 'spark_skill_targets', None))

def _decide(ctx, rows, targets, mode, min_stars, requirements):
    """Evaluate the keep rule, reading past the fold only if that could change it.

    Three reasons this does not simply always scroll. Hidden rows can only add
    sparks, so a rule already satisfied stays satisfied. Blue and pink are
    always in the top three rows, so a rule made only of those can never be
    changed by scrolling. And dragging a list the game flings is the riskiest
    thing here, so it earns its place only when the answer is otherwise "no".

    Returns (rows_used, hit).
    """
    hit = spark_rule_check(rows, targets, mode, min_stars, requirements)
    if hit or not requirements:
        return rows, hit
    try:
        if spark_list_at_bottom(ctx.ctrl.get_screen()):
            return rows, hit
        log.info("🎲 No match in the visible sparks and the list runs on - "
                 "scrolling to read the rest")
        full = read_all_spark_rows(ctx, first_page=rows)
    except Exception as e:
        # A failed scroll must not read as "the spark is not there": say so.
        log.warning(f"🎲 Could not read past the fold ({e}) - deciding on the "
                    f"{len(rows)} visible row(s)")
        return rows, hit
    if len(full) > len(rows):
        log.info(f"🎲 Read {len(full)} sparks in full: {_spark_rows_text(full)}")
    return full, spark_rule_check(full, targets, mode, min_stars, requirements)


def _spark_rows_text(rows) -> str:
    return ", ".join(f"{r['color'] or '?'}:{r['name'] or '?'}({r['canonical'] or '-'}) {r['stars']}*"
                     for r in rows) or "(none)"

def _save_spark_debug(ctx, tag: str, img=None):
    """Keep captures of every spark reroll step so misdetections on the new
    screens can be diagnosed (and templates recalibrated) from a real run."""
    try:
        os.makedirs('screenshot/spark_reroll', exist_ok=True)
        if img is None:
            img = ctx.ctrl.get_screen()
        cv2.imwrite(f'screenshot/spark_reroll/{time.strftime("%Y%m%d_%H%M%S")}_{tag}.png', img)
    except Exception as e:
        log.debug(f"spark debug capture failed: {e}")

def _spark_selection_show_view(ctx, want: str) -> bool:
    """Switch the Spark Selection carousel to the wanted view ('rerolled' or
    'original') using the arrows. Returns True when the subtitle confirms it."""
    for attempt in range(4):
        img = ctx.ctrl.get_screen()
        view = parse_spark_selection_title(img)
        if view == want:
            return True
        ctx.ctrl.click(SPARK_SEL_RIGHT_ARROW[0], SPARK_SEL_RIGHT_ARROW[1],
                       "Spark Selection - switch set")
        time.sleep(1.5)
    return False

def _spark_selection_confirm(ctx) -> bool:
    """Click the centered green Confirm on the Spark Selection screen."""
    x1, y1, x2, y2 = SPARK_SEL_CONFIRM_AREA
    btn = find_green_button(ctx.ctrl.get_screen(), x1, y1, x2, y2)
    if btn is None:
        return False
    ctx.ctrl.click(btn[0], btn[1], "Spark Selection - Confirm")
    return True

def script_factor_receive(ctx):
    # The Spark Selection screen (after a reroll) can also match this UI's
    # "Sparks" label; never blind-click the confirm point there.
    if getattr(ctx.career, 'spark_reroll_phase', '') in ('reroll_clicked', 'selected') \
            and ctx.current_screen is not None \
            and is_spark_selection_screen(ctx.current_screen):
        handle_spark_selection(ctx)
        return
    if ctx.career.parse_factor_done:
        ctx.ctrl.click_by_point(CULTIVATE_FACTOR_RECEIVE_CONFIRM)
    else:
        time.sleep(2)
        parse_factor(ctx)

def script_factor_reroll(ctx):
    # End-of-run sparks screen with the reroll offer (30 TP), added in the
    # July 2026 patch. Factors still get parsed here like on FACTOR_RECEIVE.
    if not ctx.career.parse_factor_done:
        time.sleep(2)
        parse_factor(ctx)
        return
    # Stopping only makes sense for a single-run loop session: the task ends
    # with the game left on this screen so the user can reroll manually.
    detail = ctx.task.detail
    d = ctx.career
    single_run = (ctx.task.task_execute_mode == TaskExecuteMode.TASK_EXECUTE_MODE_LOOP
                  and (getattr(detail, 'loop_count', 0) or 0) == 1)
    if getattr(detail, 'stop_at_spark_reroll', False) and single_run:
        log.info("🎲 Spark reroll screen reached - stopping so the user can reroll manually")
        ctx.task.end_task(TaskStatus.TASK_STATUS_SUCCESS, EndTaskReason.STOP_AT_SPARK_REROLL)
        return

    # Couldn't afford the reroll (info.py declined the TP-restore prompt): we
    # are back on the spark screen, so keep the original roll and finish.
    if getattr(d, 'spark_reroll_phase', '') == 'abort':
        log.info("🎲 Reroll unaffordable - keeping the original sparks")
        d.spark_reroll_phase = 'done'
        d.spark_reroll_result = {'rerolled': False, 'chosen': 'original',
                                 'reason': 'not enough TP to reroll'}
        ctx.career.career_result['spark_reroll'] = d.spark_reroll_result
        ctx.ctrl.click_by_point(CULTIVATE_FACTOR_REROLL_SKIP)
        return

    # Rerolling switched on with nothing targeted: read the roll anyway and say
    # what it was. This decides nothing and clicks nothing - the skip below
    # still runs - but without it the screen goes by unexamined, and "what did
    # the bot see" is the only question worth asking about a spark reader.
    # Once per career; the flag lives on the run context, which is rebuilt each
    # time.
    if (getattr(detail, 'spark_reroll_enabled', False)
            and not _spark_reroll_active(ctx)
            and not getattr(d, 'spark_read_logged', False)):
        d.spark_read_logged = True
        try:
            _save_spark_debug(ctx, "readonly")
            rows = parse_spark_rows(ctx)
            log.info(f"🎲 Sparks read, nothing targeted: {_spark_rows_text(rows)}")
            if spark_list_at_bottom(ctx.ctrl.get_screen()):
                log.info("🎲 Whole list visible - nothing below the fold")
            else:
                full = read_all_spark_rows(ctx, first_page=rows)
                _save_spark_debug(ctx, "readonly_scrolled")
                log.info(f"🎲 Read past the fold: {len(rows)} visible -> "
                         f"{len(full)} in full: {_spark_rows_text(full)}")
        except Exception as e:
            log.warning(f"🎲 Read-only spark read failed: {e}")

    if _spark_reroll_active(ctx) and getattr(d, 'spark_reroll_phase', '') == '':
        time.sleep(1)
        rows = parse_spark_rows(ctx)
        log.info(f"🎲 Spark roll 1: {_spark_rows_text(rows)}")
        targets = detail.spark_reroll_targets
        min_stars = getattr(detail, 'spark_reroll_min_stars', 3)
        mode = getattr(detail, 'spark_reroll_mode', 'or')
        wanted_skills = getattr(detail, 'spark_skill_targets', []) or []
        rows, hit = _decide(ctx, rows, targets, mode, min_stars, wanted_skills)
        if hit:
            log.info(f"🎲 Desired spark(s) '{hit}' present at the required stars - keeping this roll")
            d.spark_reroll_phase = 'keep'
            d.spark_reroll_result = {'rerolled': False, 'chosen': 'original',
                                     'reason': f"roll 1 has {hit}"}
            ctx.career.career_result['spark_reroll'] = d.spark_reroll_result
            ctx.ctrl.click_by_point(CULTIVATE_FACTOR_REROLL_SKIP)
            return
        if not rows:
            log.warning("🎲 Could not parse any spark rows - confirming without reroll")
            d.spark_reroll_phase = 'done'
            ctx.ctrl.click_by_point(CULTIVATE_FACTOR_REROLL_SKIP)
            return
        screen = ctx.ctrl.get_screen(to_gray=True)
        btn = image_match(screen, UI_FACTOR_REROLL)
        if btn.find_match:
            log.info("🎲 No desired spark in roll 1 - rerolling (30 TP)")
            _save_spark_debug(ctx, "roll1")
            d.spark_reroll_phase = 'reroll_clicked'
            d.spark_reroll_clicks = 0
            ctx.ctrl.click(btn.center_point[0], btn.center_point[1], "Reroll Sparks")
        else:
            log.warning("🎲 Reroll button not found - confirming without reroll")
            d.spark_reroll_phase = 'done'
            ctx.ctrl.click_by_point(CULTIVATE_FACTOR_REROLL_SKIP)
        return

    if getattr(d, 'spark_reroll_phase', '') == 'reroll_clicked':
        # We are back on the reroll screen although the reroll was requested:
        # the confirmation dialog was probably dismissed. Retry a few times.
        d.spark_reroll_clicks += 1
        if d.spark_reroll_clicks > 5:
            log.warning("🎲 Reroll did not go through (TP too low?) - confirming without reroll")
            d.spark_reroll_phase = 'done'
            ctx.ctrl.click_by_point(CULTIVATE_FACTOR_REROLL_SKIP)
            return
        screen = ctx.ctrl.get_screen(to_gray=True)
        btn = image_match(screen, UI_FACTOR_REROLL)
        if btn.find_match:
            ctx.ctrl.click(btn.center_point[0], btn.center_point[1], "Reroll Sparks (retry)")
        else:
            time.sleep(1)
        return

    ctx.ctrl.click_by_point(CULTIVATE_FACTOR_REROLL_SKIP)

def handle_spark_selection(ctx):
    """Spark Selection screen (after Reroll Sparks): a carousel showing one
    set at a time; Confirm keeps the displayed set. Keeps the rerolled set
    when it satisfies the desired-spark check; otherwise keeps the set with
    the most white sparks."""
    detail = ctx.task.detail
    d = ctx.career

    if getattr(d, 'spark_reroll_phase', '') == 'reroll_clicked':
        time.sleep(1.5)
        img = ctx.ctrl.get_screen()
        _save_spark_debug(ctx, "selection", img)
        targets = detail.spark_reroll_targets
        min_stars = getattr(detail, 'spark_reroll_min_stars', 3)
        mode = getattr(detail, 'spark_reroll_mode', 'or')

        if not _spark_selection_show_view(ctx, 'rerolled'):
            log.warning("🎲 Could not switch to the rerolled set - keeping what is shown")
            d.spark_reroll_phase = 'selected'
            d.spark_reroll_clicks = 0
            _spark_selection_confirm(ctx)
            return

        rerolled_rows = parse_spark_rows(ctx)
        log.info(f"🎲 Rerolled sparks: {_spark_rows_text(rerolled_rows)}")
        wanted_skills = getattr(detail, 'spark_skill_targets', []) or []
        rerolled_rows, hit = _decide(ctx, rerolled_rows, targets, mode,
                                     min_stars, wanted_skills)
        if hit:
            choose_rerolled = True
            reason = f"rerolled set has {hit}"
            original_rows = []
        else:
            # Neither set qualifies. Prefer the set with more white sparks. A
            # set always leads with the same 3 non-white rows (blue+pink+green),
            # so more sparks == more whites, and the scrollbar thumb reads that
            # directly: a shorter thumb = more rows below the fold. This beats
            # scrolling + re-OCRing each list (the in-game list flings rather
            # than scrolls a fixed step).
            ratio_rerolled = spark_scrollbar_ratio(ctx.ctrl.get_screen())
            if not _spark_selection_show_view(ctx, 'original'):
                log.warning("🎲 Could not switch to the original set - keeping the rerolled one")
                _spark_selection_show_view(ctx, 'rerolled')
                choose_rerolled = True
                reason = "carousel switch failed"
                original_rows = []
            else:
                original_rows = parse_spark_rows(ctx)
                log.info(f"🎲 Original sparks: {_spark_rows_text(original_rows)}")
                ratio_original = spark_scrollbar_ratio(ctx.ctrl.get_screen())
                log.info(f"🎲 Neither set has a desired spark - scrollbar thumb: "
                         f"rerolled {ratio_rerolled:.2f} vs original {ratio_original:.2f} "
                         f"(smaller = more sparks)")
                if abs(ratio_rerolled - ratio_original) > 0.05:
                    choose_rerolled = ratio_rerolled < ratio_original
                    reason = (f"more white sparks by scrollbar "
                              f"(thumb {ratio_rerolled:.2f} vs {ratio_original:.2f})")
                elif (ratio_rerolled >= FULLY_VISIBLE
                        and ratio_original >= FULLY_VISIBLE
                        and len(rerolled_rows) != len(original_rows)):
                    # Both thumbs are the no-scrollbar sentinel, so neither
                    # list has anything below the fold and `parse_spark_rows`
                    # has already counted every row of both. Counting is then
                    # exact, and better evidence than the thumb ever is.
                    #
                    # Without this the tie fell through to total stars, which
                    # answers a different question: a three-row set with high
                    # stars beat an eight-row one. "The set with the most
                    # sparks" is the rule, so count the sparks.
                    choose_rerolled = len(rerolled_rows) > len(original_rows)
                    reason = (f"more sparks, both lists fully visible "
                              f"({len(rerolled_rows)} vs {len(original_rows)} rows)")
                else:
                    # Genuinely the same length: fall back to total visible stars
                    stars_original = sum(r['stars'] for r in original_rows)
                    stars_rerolled = sum(r['stars'] for r in rerolled_rows)
                    choose_rerolled = stars_rerolled > stars_original
                    reason = (f"list length tied (thumb {ratio_rerolled:.2f}); "
                              f"total stars {stars_rerolled} vs {stars_original}")

        chosen = 'rerolled' if choose_rerolled else 'original'
        log.info(f"🎲 Choosing the {chosen} spark set ({reason})")
        d.spark_reroll_result = {
            'rerolled': True, 'chosen': chosen, 'reason': reason,
            'original': [[r['name'], r['stars']] for r in original_rows],
            'new': [[r['name'], r['stars']] for r in rerolled_rows],
        }
        ctx.career.career_result['spark_reroll'] = d.spark_reroll_result
        if choose_rerolled:
            # keep the task report in sync with the kept set
            ctx.career.career_result['factor_list'] = \
                [[r['name'], r['stars']] for r in rerolled_rows if r['name']]

        if not _spark_selection_show_view(ctx, chosen):
            log.warning(f"🎲 Could not navigate to the {chosen} set - confirming current view")
        d.spark_reroll_phase = 'selected'
        d.spark_reroll_clicks = 0
        _save_spark_debug(ctx, f"confirming_{chosen}")
        if not _spark_selection_confirm(ctx):
            log.warning("🎲 Confirm button not found on the Spark Selection screen")
        return

    if getattr(d, 'spark_reroll_phase', '') == 'selected':
        # still on the selection screen: the confirm click missed
        d.spark_reroll_clicks += 1
        if d.spark_reroll_clicks > 4:
            log.error("🎲 Could not leave the Spark Selection screen - see "
                      "screenshot/spark_reroll/ captures")
            d.spark_reroll_phase = 'failed'
            return
        if not _spark_selection_confirm(ctx):
            ctx.ctrl.click(360, 1178, "Spark Selection - Confirm (fallback)")


# Keywords that mean "you cannot afford this reroll". The game asks in two
# steps when TP is short: a compact "You need N more TP to reroll Sparks.
# Restore TP?" and then the full Recover TP screen.
CANT_AFFORD = ('more tp', 'restore tp', 'recover', 'recovery', 'shop',
               'insufficient', 'not enough', 'carats')


def intercept_dialog(ctx, header_pos) -> bool:
    """Handle a dialog raised while a reroll is in flight. True when handled.

    These dialogs have to be judged by their body text, not their title. The
    title dispatch would click a point behind the dialog, and the two that
    matter here - the 30 TP reroll confirmation and the "keep this set" confirm
    - are not distinguishable by title alone.

    Declining costs nothing but the reroll. The career is already finished by
    this point, so running out of TP here is not a failed run: it keeps the
    original sparks and moves on. That is why this has to come before the
    TP-recovery handler, which would end the career instead.
    """
    career = getattr(ctx, 'career', None)
    phase = getattr(career, 'spark_reroll_phase', '') if career else ''
    if phase not in ('reroll_clicked', 'selected', 'abort'):
        return False

    img = cv2.cvtColor(ctx.current_screen, cv2.COLOR_BGR2GRAY)
    bottom = header_pos[1][1]
    body = (ocr_line(img[bottom + 10:bottom + 260, 70:650]) or '').lower()
    log.info(f"Dialog during spark reroll (phase {phase!r}): {body[:80]!r}")

    if any(k in body for k in CANT_AFFORD) and tp.allowed(ctx)             and phase == 'reroll_clicked':
        # The task allows spending, so restore rather than abandon the reroll.
        if tp.step(ctx, body, header_pos):
            return True
        log.warning("TP restore did not proceed - keeping the original sparks")

    if any(k in body for k in CANT_AFFORD):
        # Bail out fast rather than ping-ponging on TP dialogs. A career that
        # ends under 30 TP hits exactly this.
        tries = getattr(career, 'spark_reroll_abort_tries', 0) + 1
        career.spark_reroll_abort_tries = tries
        career.spark_reroll_clicks = 99
        career.spark_reroll_phase = 'abort'
        log.warning(f"Not enough TP to reroll (attempt {tries}) - declining and "
                    f"keeping the original sparks")
        ok = find_green_button(ctx.current_screen, 70, bottom, 660, 1270)
        if tries <= 2 and ok:
            # Cancel is the white button mirroring the green one.
            ctx.ctrl.click(720 - ok[0], ok[1], "Decline TP restore (keep the first roll)")
        else:
            ctx.ctrl.click_by_point(ESCAPE)
        time.sleep(1)
        return True

    if phase == 'reroll_clicked' or any(
            k in body for k in ('spark', 'factor', 'receive', 'select', 'keep')):
        # These range from compact (Confirm Reroll) to nearly full screen (Keep
        # this set of Sparks?), so search everything below the title bar.
        ok = find_green_button(ctx.current_screen, 70, bottom, 660, 1270)
        if ok:
            ctx.ctrl.click(ok[0], ok[1], "Spark reroll dialog confirm")
            if phase == 'selected':
                career.spark_reroll_phase = 'done'   # stop intercepting
            time.sleep(1)
            return True

    return False
