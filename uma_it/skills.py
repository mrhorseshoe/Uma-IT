"""Buying skills at the end of a career.

Off unless the task asks for it. When it is on, the learn-skills screen is read
page by page, every purchasable skill is matched against a priority list, and
as many as the skill points allow are bought in priority order.

The parent's version of this is 300 lines; this is about half. What is gone:

* **Manual-purchase mode.** Six repeated "has the user finished buying by
  hand?" blocks, feeding a flow that POSTs to the web server and then blocks
  the bot thread in a `while True` poll, with a bare `input()` as its fallback.
  The setting is gone too, rather than left dead.
* **Turn-by-turn bookkeeping.** `turn_info.turn_learn_skill_done` and the URA
  event-weight update have no meaning here: the game plays the career, so there
  are no turns and no event weights to reset.

One thing that is *not* a simplification, and matters. The buying pass removes
skills from the priority list as it learns them, so it does not try to re-buy
them on the next page. In the parent that list is a per-run copy. Here the
task's list is serialized to disk, so the copy is explicit - see
`CareerContext.skills_wanted`. Editing the task's own list would delete skills
from the saved preset permanently.
"""
import re
import time

import cv2

import bot.base.log as logger
from bot.recog.image_matcher import compare_color_equal
from bot.recog.ocr import ocr_line

from uma_it.asset.point import (
    RETURN_TO_CULTIVATE_FINISH,
    CULTIVATE_LEARN_SKILL_CONFIRM,
)
from uma_it.const import SKILL_LEARN_PRIORITY_LIST
from uma_it.parse import find_skill, get_skill_list

log = logger.get_logger(__name__)

# Where the skill point total sits on the learn-skills screen.
SKILL_POINTS_REGION = (400, 440, 490, 665)   # y1, y2, x1, x2

# Pixels that say "the list can still scroll", and their expected colour.
MORE_BELOW_PIXEL = (1006, 701)
MORE_ABOVE_PIXEL = (488, 701)
SCROLLBAR_COLOR = [211, 209, 219]


def _leave(ctx, why: str):
    log.info(why)
    ctx.career.learn_skill_done = True
    ctx.ctrl.click_by_point(RETURN_TO_CULTIVATE_FINISH)


def _read_every_page(ctx, wanted, blacklist):
    """Scroll the whole list, collecting every skill it shows."""
    seen = []
    while ctx.task.running():
        img = ctx.ctrl.get_screen()
        for skill in get_skill_list(img, wanted, blacklist):
            if skill not in seen:
                seen.append(skill)
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        if not compare_color_equal(rgb[MORE_BELOW_PIXEL], SCROLLBAR_COLOR):
            break
        ctx.ctrl.swipe(x1=23, y1=1000, x2=23, y2=636, duration=1000,
                       name="scroll the skill list")
        time.sleep(1)
    return seen


def _read_skill_points(ctx) -> int:
    y1, y2, x1, x2 = SKILL_POINTS_REGION
    digits = re.sub(r'\D', '', ocr_line(ctx.ctrl.get_screen()[y1:y2, x1:x2]) or '')
    return int(digits) if digits else 0


def _choose(skills, wanted, budget, only_listed=False):
    """Pick what to buy: priority order first, then spend what is left over.

    Every tier is considered, and within a tier an unaffordable skill is
    skipped rather than ending the tier. That is the difference between this
    and the parent, which breaks on both counts - so one expensive skill early
    in a tier stopped the whole tier, and one unaffordable tier stopped every
    tier below it. Measured: a 300-point budget facing a 400-point skill bought
    nothing at all, twice over, with affordable skills sitting right there.

    Nothing is being saved for later. This runs at the end of a career, so a
    point not spent here is lost.

    Order still matters: tiers are visited in order and, within a tier, highest
    hint level first, so cheap filler can only take budget the good skills had
    already declined.

    `only_listed` stops at the last tier the user named, leaving the
    everything-else bucket unbought - which is what
    `learn_skill_only_user_provided` asks for.
    """
    chosen, chosen_raw, spent = [], [], 0
    # get_skill_list files anything the user did not name one past the last
    # tier, so that bucket is the natural last stop.
    levels = len(wanted) if only_listed else len(wanted) + 1
    for level in range(levels):
        at_level = sorted(
            [s for s in skills if s["priority"] == level and s["available"] is True],
            key=lambda s: -int(s.get("hint_level", 0)))
        for skill in at_level:
            # Re-checked inside the loop, not just when at_level was built: a
            # gold skill bought earlier in this same tier marks the skill below
            # it unavailable, and the parent misses that because it filters
            # once up front.
            if skill["available"] is not True:
                continue
            if spent + skill["skill_cost"] > budget:
                log.debug(f"Skipping {skill['skill_name']!r} - costs "
                          f"{skill['skill_cost']}, {budget - spent} left")
                continue
            spent += skill["skill_cost"]
            chosen.append(skill["skill_name"])
            chosen_raw.append(skill["skill_name_raw"])
            log.info(f"Buying {skill['skill_name']!r} "
                     f"(cost {skill['skill_cost']}, spent {spent}/{budget})")
            # A gold skill supersedes the skill bound below it; that one can no
            # longer be bought separately.
            if skill["gold"] is True and skill.get("subsequent_skill"):
                for other in skills:
                    if other["skill_name"] == skill["subsequent_skill"]:
                        other["available"] = False
    return chosen, chosen_raw, spent


def script_learn_skill(ctx):
    """The learn-skills screen."""
    career = ctx.career
    detail = ctx.task.detail

    if career.learn_skill_done:
        _leave(ctx, "Skills already bought this pass - returning")
        return

    remaining = career.skills_wanted(detail)
    blacklist = list(getattr(detail, 'learn_skill_blacklist', None) or [])

    if getattr(detail, 'learn_skill_only_user_provided', False):
        if not remaining:
            _leave(ctx, "No skills left in the task's list - returning")
            return
        wanted = remaining
    else:
        wanted = remaining or SKILL_LEARN_PRIORITY_LIST

    log.info("Skill priorities: " + " | ".join(
        f"{i}: {', '.join(tier)}" for i, tier in enumerate(wanted) if tier))
    if blacklist:
        log.info("Blacklist: " + ", ".join(blacklist))

    skills = _read_every_page(ctx, wanted, blacklist)
    already = [s.get('skill_name_raw') or s.get('skill_name')
               for s in skills if s.get('available') is False]
    if already:
        log.info("Already learned: " + ", ".join(n for n in already if n))

    # A gold skill is listed immediately above the skill it supersedes.
    for i, skill in enumerate(skills[:-1]):
        if skill["gold"] is True:
            skill["subsequent_skill"] = skills[i + 1]["skill_name"]

    skills.sort(key=lambda s: s["priority"])
    budget = _read_skill_points(ctx)
    log.info(f"{budget} skill points, {len(skills)} skills on the screen")

    only_listed = bool(getattr(detail, 'learn_skill_only_user_provided', False))
    chosen, chosen_raw, spent = _choose(skills, wanted, budget, only_listed)
    log.info(f"Buying {len(chosen)} skill(s) for {spent} points: "
             f"{', '.join(chosen) if chosen else 'none'}")

    # Say what is left, and whether anything could still have been bought with
    # it. "Do not leave points on the table" is only checkable if the log says
    # how many were left over.
    left = budget - spent
    affordable = [x for x in skills
                  if x["available"] is True and x["skill_name"] not in chosen
                  and x["skill_cost"] <= left
                  and (not only_listed or x["priority"] < len(wanted))]
    if affordable:
        log.warning(f"{left} skill points unspent with {len(affordable)} skill(s) "
                    f"still affordable - cheapest "
                    f"{min(x['skill_cost'] for x in affordable)}")
    else:
        log.info(f"{left} skill points unspent; nothing left costs that little")

    # Align the list back to the top before clicking.
    ctx.ctrl.swipe(x1=23, y1=950, x2=23, y2=968, duration=100, name="align the skill list")
    time.sleep(1)

    # Drop what is now learned - or was already - from this run's list, so a
    # second pass does not go looking for them again.
    learned = set(chosen_raw) | {s['skill_name_raw'] for s in skills
                                 if s['available'] is False}
    for tier in remaining:
        for name in list(tier):
            if name in learned:
                tier.remove(name)
    career.remaining_skills = [tier for tier in remaining if tier]

    if not chosen:
        _leave(ctx, "Nothing affordable to buy - returning")
        return

    to_click = list(chosen)
    while True:
        img = ctx.ctrl.get_screen()
        if find_skill(ctx, img, to_click, learn_any_skill=False):
            career.learn_skill_selected = True
        if not to_click:
            break
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        if not compare_color_equal(rgb[MORE_ABOVE_PIXEL], SCROLLBAR_COLOR):
            break
        ctx.ctrl.swipe(x1=23, y1=636, x2=23, y2=1000, duration=1000,
                       name="scroll the skill list back")
        time.sleep(1)

    career.learn_skill_done = True
    log.info("Skill buying done - confirming")
    ctx.ctrl.click_by_point(CULTIVATE_LEARN_SKILL_CONFIRM)
