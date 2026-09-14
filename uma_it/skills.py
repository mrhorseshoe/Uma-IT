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
    CULTIVATE_LEARN_SKILL_CONFIRM_AGAIN,
)
from uma_it.const import SKILL_LEARN_PRIORITY_LIST
from uma_it.parse import SKILL_GRADE_SUFFIX, find_skill, get_skill_list

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


def script_confirm_learn(ctx):
    """"Learn the above skills?" - the click that actually spends the points.

    Its own screen, not a second crop of the skill screen, which is what the
    manifest used to call it. `CONFIRMATION_LEARNSKILL_BUTTON` is a crop of
    this dialog's **Learn** button, so it matches this dialog and nothing else -
    and routing it to `script_learn_skill` meant arriving with the buying pass
    already done, taking the `_leave` branch, and clicking Back at (90, 1190).

    That point is inside this dialog, on **Cancel**. So the bot cancelled its
    own purchase, was asked "Exit without learning skills?", agreed, and went
    round again. On 11 Sep one career made four passes over the same 4108
    points, selecting about 4000 of them each time and discarding every one.
    The tell was in the logs the whole time: the skill point total read 4108 at
    the start of every pass.
    """
    log.info("Confirmation: 'Learn the above skills?' - learning")
    ctx.ctrl.click_by_point(CULTIVATE_LEARN_SKILL_CONFIRM_AGAIN)
    time.sleep(1)


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


def _settled_skill_points(ctx, tries: int = 6) -> int:
    """The skill point total, read once the screen has stopped moving.

    Read straight after the screen opens, the total can come back 0. On 14 Sep
    a second pass logged '0 skill points, 6 skills on the screen' with about
    800 points left, decided nothing was affordable and finished the career -
    and the second pass is the one that picks up what the first missed, and
    the only one that can buy a ◎. That frame's list read was short as well,
    so the whole screen had not settled, which is why this runs before the
    list is read rather than after.

    Two equal non-zero reads a second apart are believed. A total that never
    rises above 0 in `tries` reads is believed as well.
    """
    last, seen = None, 0
    for _ in range(tries):
        points = _read_skill_points(ctx)
        if points and points == last:
            return points
        if points:
            seen = points
        last = points
        time.sleep(1)
    if seen:
        log.warning(f"Skill points never read the same twice - using {seen}")
    return seen


def _scroll_to_bottom(ctx, limit: int = 20):
    for _ in range(limit):
        rgb = cv2.cvtColor(ctx.ctrl.get_screen(), cv2.COLOR_BGR2RGB)
        if not compare_color_equal(rgb[MORE_BELOW_PIXEL], SCROLLBAR_COLOR):
            return
        ctx.ctrl.swipe(x1=23, y1=1000, x2=23, y2=636, duration=1000,
                       name="scroll the skill list")
        time.sleep(1)


def _drop_from_remaining(career, remaining, names):
    for tier in remaining:
        for name in list(tier):
            if name in names:
                tier.remove(name)
    career.remaining_skills = [tier for tier in remaining if tier]


# A ◎ is offered only once its ○ is learned, and costs about the same: across
# 11-12 Sep the ◎ came in at 1.0x to 1.22x its ○. Holding back 5/4 errs towards
# leaving points for the next pass, which spends them anyway.
UPGRADE_HOLD_BACK = (5, 4)


def circle_base(name):
    """A circle skill's name without its grade, as letters only; else None.

    OCR reads both ○ and ◎ as a capital O, so the name never says which grade
    a row is - `_choose` settles that from what this career has learned.
    """
    text = (name or '').strip()
    if not SKILL_GRADE_SUFFIX.search(text):
        return None
    return name_key(text) or None


def name_key(name):
    """A skill name as letters only, any grade symbol dropped."""
    text = SKILL_GRADE_SUFFIX.sub('', (name or '').strip())
    return re.sub(r'[^a-z]', '', text.lower())


def _choose(skills, wanted, budget, only_listed=False, circles_owned=frozenset()):
    """Pick what to buy, and what to hold back for the next pass.

    Three stages, each spending only what the ones before it left:

    1. **The priority tiers**, in order, highest hint level first in a tier.
    2. **◎ upgrades of priority skills** - a higher grade sparks more often,
       and sparks are what a parent is for. Only for circle skills bought as
       priority skills earlier in this career (the owner's rule, 14 Sep); an
       unlisted ○ gets no special treatment. A ◎ is only offered once its ○
       is learned, so it can never be bought in the pass that buys the ○.
       Each priority ○ bought here therefore holds back an estimate of its ◎
       from stage 3, and the next pass - which always follows a pass that
       bought something - finds the ◎ and buys it first. OCR cannot tell ○
       from ◎, so a circle row counts as that upgrade when its ○ is in
       `circles_owned`.
    3. **Everything else, cheapest first.** Each skill learned is another
       chance at a white spark, so the most skills for the points is the best
       use of what is left.

    An unaffordable skill is skipped, never a reason to stop. The parent
    breaks there, and a 300-point budget facing a 400-point skill bought
    nothing at all, twice over.

    `only_listed` stops after stage 1, which is what
    `learn_skill_only_user_provided` asks for.

    Returns (chosen, chosen_raw, spent, held_back).
    """
    chosen, chosen_raw = [], []
    tally = {'spent': 0, 'held': 0}

    def buy(skill, stage, limit):
        # Re-checked per skill: a gold skill bought earlier in this same call
        # marks the skill bound below it unavailable.
        if skill["available"] is not True or skill["skill_name"] in chosen:
            return
        if tally['spent'] + skill["skill_cost"] > limit:
            log.debug(f"Skipping {skill['skill_name']!r} - costs "
                      f"{skill['skill_cost']}, {limit - tally['spent']} to spend")
            return
        tally['spent'] += skill["skill_cost"]
        chosen.append(skill["skill_name"])
        chosen_raw.append(skill["skill_name_raw"])
        log.info(f"Buying {skill['skill_name']!r} ({stage}, cost "
                 f"{skill['skill_cost']}, spent {tally['spent']}/{budget})")
        # A gold skill supersedes the skill bound below it.
        if skill["gold"] is True and skill.get("subsequent_skill"):
            for other in skills:
                if other["skill_name"] == skill["subsequent_skill"]:
                    other["available"] = False
        base = circle_base(skill["skill_name"])
        if stage == "priority" and base and base not in circles_owned and not only_listed:
            num, den = UPGRADE_HOLD_BACK
            tally['held'] += -(-skill["skill_cost"] * num // den)

    for level in range(len(wanted)):
        for skill in sorted([s for s in skills if s["priority"] == level],
                            key=lambda s: -int(s.get("hint_level", 0))):
            buy(skill, "priority", budget)
    if only_listed:
        return chosen, chosen_raw, tally['spent'], 0

    # get_skill_list files anything the user did not name one past the last tier.
    unlisted = [s for s in skills if s["priority"] == len(wanted)]
    # Matched on the name alone, symbol or not: on 14 Sep both ◎ rows OCR'd
    # with no symbol at all ('Wet Conditions '), so `circle_base` saw plain
    # names and they were bought as 'other'. Only circle skills are ever in
    # `circles_owned`, so a plain skill cannot match by accident.
    upgrades = sorted([s for s in unlisted if name_key(s["skill_name"]) in circles_owned],
                      key=lambda s: s["skill_cost"])
    for skill in upgrades:
        buy(skill, "◎ upgrade", budget)
    for skill in sorted(unlisted, key=lambda s: (s["skill_cost"],
                                                 -int(s.get("hint_level", 0)))):
        buy(skill, "other", budget - tally['held'])
    return chosen, chosen_raw, tally['spent'], tally['held']


def script_learn_skill(ctx):
    """The learn-skills screen."""
    career = ctx.career
    detail = ctx.task.detail

    if career.learn_skill_done:
        _leave(ctx, "Skills already bought this pass - returning")
        return

    remaining = career.skills_wanted(detail)
    blacklist = list(getattr(detail, 'learn_skill_blacklist', None) or [])
    only_listed = bool(getattr(detail, 'learn_skill_only_user_provided', False))

    if only_listed:
        if not remaining:
            _leave(ctx, "No skills left in the task's list - returning")
            return
        wanted = remaining
    elif any(getattr(detail, 'learn_skill_list', None) or []):
        # The task names skills, so its list stands even once this run has
        # bought all of them. This used to fall back on the run copy being
        # empty, which swapped the shipped tiers in on a later pass - ahead of
        # the ◎ upgrades that pass is there to buy.
        wanted = remaining
    else:
        wanted = SKILL_LEARN_PRIORITY_LIST

    listed = {name for tier in wanted for name in tier}
    log.info("Skill priorities: " + (" | ".join(
        f"{i}: {', '.join(tier)}" for i, tier in enumerate(wanted) if tier)
        or "all bought"))
    if blacklist:
        log.info("Blacklist: " + ", ".join(blacklist))

    budget = _settled_skill_points(ctx)
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
    log.info(f"{budget} skill points, {len(skills)} skills on the screen")

    chosen, chosen_raw, spent, held = _choose(
        skills, wanted, budget, only_listed,
        circles_owned=frozenset(career.circle_skills))
    log.info(f"Buying {len(chosen)} skill(s) for {spent} points: "
             f"{', '.join(chosen) if chosen else 'none'}")
    if held:
        log.info(f"Holding back {held} points for the ◎ upgrades the next pass "
                 f"will offer")

    # Say what is left, and whether anything could still have been bought with
    # it. "Do not leave points on the table" is only checkable if the log says
    # how many were left over.
    left = budget - spent - held
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

    # What was already learned leaves this run's list now. What is being bought
    # leaves only once it is clicked - dropping it at planning time meant a
    # missed click took the skill out of its priority tier for later passes.
    _drop_from_remaining(career, remaining,
                         {s['skill_name_raw'] for s in skills if s['available'] is False})

    if not chosen:
        _leave(ctx, "Nothing affordable to buy - returning")
        return

    to_click = list(chosen)
    for sweep in range(2):
        if sweep:
            log.warning(f"{len(to_click)} chosen skill(s) not found on the way up - "
                        f"sweeping the list again: {', '.join(to_click)}")
            _scroll_to_bottom(ctx)
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
        if not to_click:
            break

    clicked = [(name, raw) for name, raw in zip(chosen, chosen_raw)
               if name not in to_click]
    if to_click:
        log.warning(f"Could not find {len(to_click)} chosen skill(s): "
                    f"{', '.join(to_click)} - the next pass looks again")
    # Recorded only for priority skills: those are the ones whose ◎ the next
    # pass buys ahead of everything else. `listed` was taken before either
    # drop above, which edits these same tier lists in place.
    for name, raw in clicked:
        base = circle_base(name)
        if base and raw in listed:
            career.circle_skills.add(base)
    _drop_from_remaining(career, remaining, {raw for _, raw in clicked})

    career.learn_skill_done = True
    log.info("Skill buying done - confirming")
    ctx.ctrl.click_by_point(CULTIVATE_LEARN_SKILL_CONFIRM)
