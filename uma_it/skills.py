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


def _choose(skills, wanted, budget):
    """Pick what to buy: priority order, highest hint level first, within budget.

    Stops at the first priority level nothing affordable was found in, which is
    what keeps a cheap low-priority skill from being bought ahead of saving for
    the tier above it.
    """
    chosen, chosen_raw, spent = [], [], 0
    for level in range(len(wanted) + 1):
        at_level = sorted(
            [s for s in skills if s["priority"] == level and s["available"] is True],
            key=lambda s: -int(s.get("hint_level", 0)))
        for skill in at_level:
            # Re-checked inside the loop, not just when at_level was built: a
            # gold skill bought earlier in this same tier marks the skill below
            # it unavailable, and the parent misses that because it filters
            # once up front. Across tiers it works there; within one it buys
            # both and wastes the points.
            if skill["available"] is not True:
                continue
            if spent + skill["skill_cost"] > budget:
                log.debug(f"Cannot afford {skill['skill_name']!r} "
                          f"({skill['skill_cost']}, {budget - spent} left)")
                break
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
        if at_level and not any(s["skill_name"] in chosen for s in at_level):
            log.debug(f"Nothing affordable at priority {level} - stopping here")
            break
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

    chosen, chosen_raw, spent = _choose(skills, wanted, budget)
    log.info(f"Buying {len(chosen)} skill(s) for {spent} points: "
             f"{', '.join(chosen) if chosen else 'none'}")

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
