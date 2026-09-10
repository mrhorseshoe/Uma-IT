"""Reading things off the screen that no template can match.

Everything here is copied from the parent project rather than rewritten. The
constants are pixel geometry measured against the live game at 720x1280, and
the colour thresholds were tuned against real frames; both are calibration, and
calibration gets moved, not redrawn.
"""
import json
import os
import re
import time
import unicodedata
from collections import Counter
from difflib import SequenceMatcher

import cv2
import numpy

from bot.recog.image_matcher import image_match, compare_color_equal
from bot.recog.ocr import ocr_line
import bot.base.log as logger

from uma_it.asset.template import (REF_FOLLOW_SUPPORT_CARD_DETECT_LABEL,
                                   REF_FACTOR_DETECT_LABEL)

log = logger.get_logger(__name__)

# The My Agendas list holds eight slots and shows three at a time. Rows have no
# stable template - each is a user-named banner - so the green "Load List"
# buttons give the rows their y positions. Buttons are found by colour on
# purpose: the white "Save Here" button sits ~65px above each Load List and
# OVERWRITES a saved slot, so it must never be hit by accident.
AGENDA_SLOT_COUNT = 8
AGENDA_LIST_SCAN = (415, 1055)        # y range of the list viewport
AGENDA_SCROLLBAR_COLS = (692, 697)    # track reads ~209, thumb ~120


def agenda_load_buttons(origin_img):
    """Centres of the visible green "Load List" buttons, top to bottom."""
    x1, y1, x2, y2 = 520, AGENDA_LIST_SCAN[0], 700, AGENDA_LIST_SCAN[1]
    region = origin_img[y1:y2, x1:x2]
    if region.size == 0:
        return []
    b = region[:, :, 0].astype(numpy.int32)
    g = region[:, :, 1].astype(numpy.int32)
    r = region[:, :, 2].astype(numpy.int32)
    mask = ((g > 160) & (g - r > 50) & (g - b > 60) & (r < 190)).astype(numpy.uint8)
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    found = []
    for i in range(1, count):
        x, y, w_c, h_c, area = stats[i]
        if not (100 <= w_c <= 400 and 30 <= h_c <= 110):
            continue
        if not (1.5 <= w_c / max(1, h_c) <= 9):
            continue
        if area < 0.45 * w_c * h_c:
            continue
        found.append((int(x1 + centroids[i][0]), int(y1 + centroids[i][1])))
    return sorted(found, key=lambda p: p[1])


def agenda_first_visible_row(origin_img):
    """1-based index of the topmost visible row in the My Agendas list, or
    None when the scrollbar cannot be read.

    Returning None matters more than returning a number. The caller must never
    treat an unreadable scrollbar as row 1 - that assumption ran a four-race
    agenda for fifteen careers without anything in the logs showing it.
    """
    top, bot = AGENDA_LIST_SCAN
    bot = min(bot, origin_img.shape[0])
    for x in range(*AGENDA_SCROLLBAR_COLS):
        col = origin_img[top:bot, x].min(axis=1).astype(numpy.int32)
        track = numpy.where(col < 230)[0]
        if len(track) < 300:
            continue
        t0, t1 = int(track[0]), int(track[-1])
        thumb = numpy.where(col[t0:t1 + 1] < 165)[0]
        if len(thumb) < 20:
            continue
        track_len = t1 - t0
        thumb_len = int(thumb[-1] - thumb[0])
        free = track_len - thumb_len
        if free <= 0:
            return 1
        visible = AGENDA_SLOT_COUNT * thumb_len / track_len
        frac = int(thumb[0]) / free
        return int(round(1 + frac * (AGENDA_SLOT_COUNT - visible)))
    return None


def agenda_row_names(origin_img, buttons):
    """OCR the green name banner of each visible row, given its Load List
    button. The banner sits about 127px above the button; a row scrolled part
    way off the top reads badly, so anything whose banner is above the list
    viewport comes back as '' and the caller should scroll rather than guess.

    Read for the log line only. Nothing branches on a row name - that was the
    previous design, and a task saved with the name blank disabled the picker
    for eleven careers.
    """
    names = []
    top = AGENDA_LIST_SCAN[0]
    gray = cv2.cvtColor(origin_img, cv2.COLOR_BGR2GRAY)
    for _, by in buttons:
        band_top, band_bot = by - 145, by - 110
        if band_top < top:
            names.append('')
            continue
        names.append((ocr_line(gray[band_top:band_bot, 45:520]) or '').strip())
    return names


# The Scheduled / G1 / G2 / G3 boxes on the career start dialog.
AGENDA_COUNT_REGIONS = {
    'scheduled': (768, 812, 40, 260),
    'g1': (652, 690, 495, 615),
    'g2': (688, 726, 495, 615),
    'g3': (724, 762, 495, 615),
}


def agenda_schedule_counts(origin_img):
    """The Scheduled / G1 / G2 / G3 numbers from the career start dialog, or
    None if any of them cannot be read.

    These are the only visible sign that the right agenda loaded. The picker
    can load the wrong entry with no error anywhere, which is how a four-race
    schedule ran for fifteen careers unnoticed.
    """
    gray = cv2.cvtColor(origin_img, cv2.COLOR_BGR2GRAY)
    out = {}
    for key, (y0, y1, x0, x1) in AGENDA_COUNT_REGIONS.items():
        text = (ocr_line(gray[y0:y1, x0:x1]) or '').strip().lower()
        digits = re.sub(r'\D', '', re.sub(r'^(scheduled|g[123])', '', text))
        if not digits:
            return None
        out[key] = int(digits)
    return out


def find_green_button(origin_img, x1: int, y1: int, x2: int, y2: int):
    """Locate the brightest green button inside a region and return its center
    (x, y), or None. Dialog OK / confirm buttons are saturated bright green;
    buttons dimmed behind a dialog overlay fall below the thresholds.

    Used where a fixed point would be dangerous - the pending-run dialog puts
    "Delete Data" on the same screen as the button that resumes the career.
    """
    region = origin_img[y1:y2, x1:x2]
    if region.size == 0:
        return None
    b = region[:, :, 0].astype(numpy.int32)
    g = region[:, :, 1].astype(numpy.int32)
    r = region[:, :, 2].astype(numpy.int32)
    mask = ((g > 160) & (g - r > 50) & (g - b > 60) & (r < 190)).astype(numpy.uint8)
    # pick a button-shaped connected component; plain centroid fails because
    # the background art also contains large green streaks
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    best = None
    for i in range(1, count):
        x, y, w_c, h_c, area = stats[i]
        if not (100 <= w_c <= 400 and 30 <= h_c <= 110):
            continue
        if not (1.5 <= w_c / max(1, h_c) <= 9):
            continue
        # solid fill (allowing for the white label text punched out of it)
        if area < 0.45 * w_c * h_c:
            continue
        if best is None or area > best[0]:
            best = (area, int(centroids[i][0]), int(centroids[i][1]))
    if best is None:
        return None
    return x1 + best[1], y1 + best[2]


def describe_green_candidates(origin_img, x1: int, y1: int, x2: int, y2: int,
                              limit: int = 3) -> str:
    """Why `find_green_button` found nothing in this region.

    The search returns None for two very different reasons and the caller
    cannot tell them apart: either the green mask is empty - wrong region,
    wrong colour, button not on screen - or the mask is fine and every
    component was rejected by the shape filters. This reports the mask size and
    the largest few components with the geometry the filters test, so the
    answer is in the log instead of being guessed at.

    Only called on the failure path, so it costs nothing in the normal case.
    """
    try:
        region = origin_img[y1:y2, x1:x2]
        if region.size == 0:
            return "region empty"
        b = region[:, :, 0].astype(numpy.int32)
        g = region[:, :, 1].astype(numpy.int32)
        r = region[:, :, 2].astype(numpy.int32)
        mask = ((g > 160) & (g - r > 50) & (g - b > 60) & (r < 190)).astype(numpy.uint8)
        on = int(mask.sum())
        if on == 0:
            return f"no green pixels in {x2 - x1}x{y2 - y1} region (mask empty)"
        count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
        blobs = sorted(
            (int(stats[i][4]), int(stats[i][2]), int(stats[i][3])) for i in range(1, count))
        blobs.reverse()
        parts = []
        for area, w_c, h_c in blobs[:limit]:
            fill = area / max(1, w_c * h_c)
            ar = w_c / max(1, h_c)
            why = []
            if not (100 <= w_c <= 400):
                why.append("w")
            if not (30 <= h_c <= 110):
                why.append("h")
            if not (1.5 <= ar <= 9):
                why.append("ar")
            if fill < 0.45:
                why.append("fill")
            parts.append(f"{w_c}x{h_c} area={area} ar={ar:.1f} fill={fill:.2f} "
                         f"rejected_by={'+'.join(why) or 'none'}")
        return f"{on} green px, {count - 1} blobs; largest: " + "; ".join(parts)
    except Exception as e:
        return f"diagnostic failed: {e!r}"


def find_support_card(ctx, img):
    """Find and click a borrowable support card matching the task's request.

    Every card on the screen carries the same label template. Each match is
    blanked out after being read so the loop moves on to the next one rather
    than re-finding the best match forever.

    The title is fuzzy-matched at 0.7 against the name saved in the task, which
    is why that name has to match the game exactly - it is OCR'd off the card.
    The in-game master database is the source of truth for those names.
    """
    detail = ctx.task.detail
    img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    while True:
        match_result = image_match(img, REF_FOLLOW_SUPPORT_CARD_DETECT_LABEL)
        if not match_result.find_match:
            return False
        pos = match_result.matched_area
        card = img[pos[0][1] - 125:pos[1][1] + 10, pos[0][0] - 140:pos[1][0] + 380]
        # blank this label so the next pass finds the next card
        img[pos[0][1]:pos[1][1], pos[0][0]:pos[1][0]] = 0

        level_img = cv2.copyMakeBorder(card[125:145, 68:111], 20, 20, 20, 20,
                                       cv2.BORDER_CONSTANT, None, (255, 255, 255))
        name_img = cv2.copyMakeBorder(card[63:94, 132:439], 20, 20, 20, 20,
                                      cv2.BORDER_CONSTANT, None, (255, 255, 255))

        level_text = ocr_line(level_img)
        if not level_text:
            continue
        digits = re.sub(r'\D', '', level_text)
        if not digits:
            log.info("Borrow list: skipping a card whose level could not be read")
            continue
        if int(digits) < detail.follow_support_card_level:
            continue

        title = ocr_line(name_img)
        if SequenceMatcher(None, title, detail.follow_support_card_name).ratio() > 0.7:
            ctx.ctrl.click(match_result.center_point[0],
                           match_result.center_point[1] - 75,
                           f"Borrow {detail.follow_support_card_name} (level {digits})")
            return True


# --- spark reroll ---------------------------------------------------------
# Reading the end-of-career sparks screen, and the post-reroll carousel that
# lets one of the two sets be kept. Moved from the parent verbatim apart from
# the SPARK_BLUE_KEYS split noted below; the geometry and the colour
# thresholds are measurements off live 720x1280 captures.
def parse_factor(ctx):
    origin_img = ctx.ctrl.get_screen()
    img = cv2.cvtColor(origin_img, cv2.COLOR_BGR2GRAY)
    factor_list = []
    while True:
        match_result = image_match(img, REF_FACTOR_DETECT_LABEL)
        if match_result.find_match:
            factor_info = ['unknown', 0]
            pos = match_result.matched_area
            factor_info_img_gray = img[pos[0][1] - 20:pos[1][1] + 25, pos[0][0] - 630: pos[1][0] - 25]
            factor_info_img = origin_img[pos[0][1] - 20:pos[1][1] + 25, pos[0][0] - 630: pos[1][0] - 25]
            factor_name_sub_img = factor_info_img_gray[15: 60, 45:320]
            factor_name = ocr_line(factor_name_sub_img)
            factor_level = 0
            factor_level_check_point = [factor_info_img[35, 535], factor_info_img[35, 565], factor_info_img[35, 595]]
            for i in range(len(factor_level_check_point)):
                if not compare_color_equal(factor_level_check_point[i], [223, 227, 237]):
                    factor_level += 1
                else:
                    break
            img[match_result.matched_area[0][1]:match_result.matched_area[1][1],
            match_result.matched_area[0][0]:match_result.matched_area[1][0]] = 0
            factor_info[0] = factor_name
            factor_info[1] = factor_level
            factor_list.append(factor_info)
        else:
            break
    ctx.career.parse_factor_done = True
    ctx.career.career_result['factor_list'] = factor_list


# ---- Spark reroll automation ----
# Canonical spark names shown on the Global client. Blue = stats,
# pink = aptitudes; white sparks (races/skills) are open-ended and are only
# counted, never matched by name.
SPARK_BLUE_NAMES = ["Speed", "Stamina", "Power", "Guts", "Wit"]


SPARK_PINK_NAMES = ["Turf", "Dirt", "Sprint", "Mile", "Medium", "Long",
                    "Front Runner", "Pace Chaser", "Late Surger", "End Closer"]


SPARK_TARGET_NAMES = SPARK_BLUE_NAMES + SPARK_PINK_NAMES


# Geometry of the post-reroll Spark Selection screen (Global client, July
# 2026): a carousel showing one set at a time ("Rerolled Sparks" /
# "Original Sparks" subtitle with switch arrows), the same full-width spark
# rows as the sparks screen, and a centered green Confirm that keeps the
# currently displayed set. Measured from live captures.
SPARK_SEL_TITLE_AREA = (118, 186, 150, 570)   # y1, y2, x1, x2 of the subtitle


SPARK_SEL_RIGHT_ARROW = (660, 150)


SPARK_SEL_CONFIRM_AREA = (150, 1110, 570, 1250)  # x1, y1, x2, y2


def classify_spark_chip_color(bgr) -> str:
    """Classify a pixel sampled inside a spark chip. Measured chip colors
    (BGR): blue (247,194,83), pink (186,135,255), white (224,224,224)."""
    b, g, r = int(bgr[0]), int(bgr[1]), int(bgr[2])
    if b > 200 and b - r > 60 and g > 140:
        return 'blue'
    if r > 220 and r - g > 70 and b > 140:
        return 'pink'
    if g > 170 and g - r > 40 and g - b > 40:
        return 'green'
    # white chips are a light gray (~224); the screen background is nearly
    # pure white (250+), so cap the upper bound to tell them apart
    if all(205 < v < 242 for v in (b, g, r)) and max(b, g, r) - min(b, g, r) < 16:
        return 'white'
    return ''


def is_spark_star_gold(patch_mean) -> bool:
    """A filled spark star is gold; empty slots are light gray."""
    b, g, r = float(patch_mean[0]), float(patch_mean[1]), float(patch_mean[2])
    return r > 190 and 130 < g < 235 and b < 150 and r - b > 70


def match_spark_target_name(ocr_text: str) -> str:
    """Map an OCR'd spark name to a canonical blue/pink name, or ''."""
    if not ocr_text:
        return ''
    norm = re.sub(r'[^a-z]', '', ocr_text.lower())
    if not norm:
        return ''
    best_name, best_score = '', 0.0
    for name in SPARK_TARGET_NAMES:
        cand = re.sub(r'[^a-z]', '', name.lower())
        score = SequenceMatcher(None, norm, cand).ratio()
        if score > best_score:
            best_name, best_score = name, score
    return best_name if best_score >= 0.7 else ''


def _spark_star_count(origin_img, star1_x: int, y: int, pitch: int) -> int:
    """Count filled (gold) stars at the three star slots; slots read left to
    right and stop at the first empty one."""
    h, w = origin_img.shape[:2]
    stars = 0
    for i in range(3):
        x = star1_x + i * pitch
        if not (2 <= x < w - 2 and 2 <= y < h - 2):
            break
        patch = origin_img[y - 2:y + 3, x - 2:x + 3].reshape(-1, 3)
        if is_spark_star_gold(patch.mean(axis=0)):
            stars += 1
        else:
            break
    return stars


def parse_spark_rows(ctx, attempts: int = 3) -> list[dict]:
    """Parse the spark rows on the sparks screen, retrying a partial read.

    Rows whose crop comes out undersized are skipped, which happens while the
    list is still rendering just after the screen appears. Every uma finishes
    with one blue and one pink spark at the top of the list, so a read missing
    either of them is partial - and acting on it turns a satisfied roll into a
    miss, which costs a 30 TP reroll. Re-read before deciding.
    """
    rows = []
    for attempt in range(max(1, attempts)):
        rows = _parse_spark_rows_once(ctx)
        colors = {r['color'] for r in rows}
        if 'blue' in colors and 'pink' in colors:
            return rows
        if attempt < attempts - 1:
            log.info(f"🎲 Spark list read looks partial (colors: {sorted(colors) or 'none'}) "
                     f"- re-reading ({attempt + 1}/{attempts - 1})")
            time.sleep(1)
    log.warning(f"🎲 Spark list still incomplete after {attempts} reads - "
                f"deciding on {len(rows)} row(s)")
    return rows


def _parse_spark_rows_once(ctx) -> list[dict]:
    """Parse the spark rows visible on the full-width sparks screen
    (FACTOR_RECEIVE / FACTOR_REROLL, page 1). Returns
    [{'name', 'canonical', 'stars', 'color', 'y'}, ...] sorted by y."""
    origin_img = ctx.ctrl.get_screen()
    img = cv2.cvtColor(origin_img, cv2.COLOR_BGR2GRAY)
    rows = []
    while True:
        match_result = image_match(img, REF_FACTOR_DETECT_LABEL)
        if not match_result.find_match:
            break
        pos = match_result.matched_area
        row_gray = img[pos[0][1] - 20:pos[1][1] + 25, pos[0][0] - 630: pos[1][0] - 25]
        row_bgr = origin_img[pos[0][1] - 20:pos[1][1] + 25, pos[0][0] - 630: pos[1][0] - 25]
        img[pos[0][1]:pos[1][1], pos[0][0]:pos[1][0]] = 0
        if row_bgr.shape[0] < 45 or row_bgr.shape[1] < 600:
            continue
        name = ocr_line(row_gray[15:60, 45:320])
        # chip color from the left margin of the chip, clear of icon and text
        chip = row_bgr[25:45, 5:20].reshape(-1, 3)
        color = classify_spark_chip_color(numpy.median(chip, axis=0))
        # star slots match the existing parse_factor geometry (row-relative)
        stars = _spark_star_count(row_bgr, 535, 35, 30)
        if stars == 0:
            # fall back to the legacy empty-slot check
            for check_x in (535, 565, 595):
                if not compare_color_equal(row_bgr[35, check_x], [223, 227, 237]):
                    stars += 1
                else:
                    break
        rows.append({'name': name, 'canonical': match_spark_target_name(name),
                     'stars': stars, 'color': color, 'y': int(pos[0][1])})
    rows.sort(key=lambda x: x['y'])
    return rows


def parse_spark_selection_title(origin_img) -> str:
    """OCR the Spark Selection carousel subtitle. Returns 'rerolled',
    'original', or '' when this is not the selection screen."""
    y1, y2, x1, x2 = SPARK_SEL_TITLE_AREA
    crop = origin_img[y1:y2, x1:x2]
    if crop.size == 0:
        return ''
    text = (ocr_line(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)) or '').lower()
    if 'reroll' in text:
        return 'rerolled'
    if 'original' in text:
        return 'original'
    return ''


def is_spark_selection_screen(origin_img) -> bool:
    """The Spark Selection screen shows a 'Rerolled Sparks' / 'Original
    Sparks' subtitle and a centered green Confirm button."""
    if parse_spark_selection_title(origin_img) == '':
        return False
    x1, y1, x2, y2 = SPARK_SEL_CONFIRM_AREA
    return find_green_button(origin_img, x1, y1, x2, y2) is not None


# Right-edge scrollbar of the spark list. The thumb length is inversely
# proportional to the number of sparks: a shorter thumb = more rows below the
# fold. Comparing the two sets' thumbs is far more robust than scrolling and
# re-OCRing each list. Measured on 720x1280 captures (thumb column x~702).
SPARK_SCROLLBAR_SCAN = (190, 915)   # y range covering the list viewport


def measure_spark_scrollbar(origin_img):
    """Return (thumb_ratio, thumb_len, track_len, x) for the spark list
    scrollbar, or None if none is visible (list fits one page). The scrollbar
    is a muted low-saturation grey-purple column; saturated chip pixels from a
    mid-slide carousel frame disqualify a column, so only settled frames read.
    thumb_ratio = thumb_len/track_len; smaller => more sparks."""
    top, bot = SPARK_SCROLLBAR_SCAN
    h, w = origin_img.shape[:2]
    bot = min(bot, h)
    best = None
    for x in range(697, 712):
        col = origin_img[top:bot, x].astype(numpy.int32)
        sat = col.max(axis=1) - col.min(axis=1)
        bright = col.min(axis=1)
        scrollbar_px = (sat < 40) & (bright < 245)
        if scrollbar_px.mean() < 0.85 or scrollbar_px.sum() < 200:
            continue
        idx = numpy.where(scrollbar_px)[0]
        track_top, track_bot = idx[0], idx[-1]
        track_len = int(track_bot - track_top)
        if track_len < 300:
            continue
        thumb_mask = origin_img[top + track_top:top + track_bot, x].min(axis=1) < 195
        # longest contiguous run of thumb pixels (the thumb is one block)
        best_run = run = 0
        for v in thumb_mask:
            run = run + 1 if v else 0
            if run > best_run:
                best_run = run
        ratio = best_run / max(1, track_len)
        if best is None or track_len > best[2]:
            best = (round(ratio, 3), int(best_run), track_len, x)
    return best


def spark_scrollbar_ratio(origin_img) -> float:
    """Thumb/track ratio of the spark list scrollbar; 1.0 when the list fits
    one page (no scrollbar). Smaller means more sparks."""
    m = measure_spark_scrollbar(origin_img)
    return m[0] if m else 1.0


SPARK_BLUE_KEYS = {'speed', 'stamina', 'power', 'guts', 'wit'}


def spark_rows_check(rows: list[dict], targets, mode: str = 'or', default_min_stars: int = 3) -> str:
    """Check parsed spark rows against the desired sparks.

    targets is a dict {spark_name: min_stars}; a legacy flat list means
    default_min_stars for every entry. An uma has one blue and one pink spark,
    so within each group any desired spark counts (implicit OR). mode 'and'
    additionally requires a hit in BOTH groups when both have desired sparks;
    'or' needs a hit in either. Returns a description of the match, or ''.
    """
    if isinstance(targets, list):
        targets = {t: default_min_stars for t in targets}
    norm = {}
    for k, v in (targets or {}).items():
        name = str(k).strip().lower()
        if name:
            try:
                norm[name] = min(3, max(1, int(v)))
            except Exception:
                norm[name] = default_min_stars
    if not norm:
        return ''
    blue_hit = ''
    pink_hit = ''
    for row in rows:
        name = (row.get('canonical') or '').lower()
        if name in norm and row.get('stars', 0) >= norm[name]:
            if name in SPARK_BLUE_KEYS:
                blue_hit = blue_hit or row['canonical']
            else:
                pink_hit = pink_hit or row['canonical']
    blue_wanted = any(n in SPARK_BLUE_KEYS for n in norm)
    pink_wanted = any(n not in SPARK_BLUE_KEYS for n in norm)
    if mode == 'and' and blue_wanted and pink_wanted:
        if blue_hit and pink_hit:
            return blue_hit + ' + ' + pink_hit
        return ''
    return blue_hit or pink_hit


# --- skill buying ---------------------------------------------------------
# Reading the skill list off the learn-skills screen: names, costs, hint
# levels, and whether each is still purchasable. Moved from the parent
# verbatim apart from the skills-database path. The OCR of a skill name is
# fuzzy-matched against the shipped database to canonicalise it, because the
# names carry symbols (a trailing circle) that OCR renders inconsistently.
skills_database_cache = None


def load_skills_database():
    global skills_database_cache
    if skills_database_cache is not None:
        return skills_database_cache
    try:
        json_path = os.path.join('resource', 'uma_it', 'skills.json')
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        names = []
        for item in data:
            name = item.get('name')
            if name:
                names.append(str(name))
        skills_database_cache = names
        return names
    except Exception:
        skills_database_cache = []
        return skills_database_cache


def normalize_text_for_match(text: str) -> str:
    if not text:
        return ""
    t = unicodedata.normalize('NFKD', str(text))
    t = t.lower().strip()
    t = re.sub(r"[^a-z0-9]+", " ", t)
    t = " ".join(t.split())
    return t


def build_bigrams(text: str) -> Counter:
    return Counter(text[i:i+2] for i in range(len(text) - 1)) if len(text) >= 2 else Counter()


def jaccard_counter_ratio(a: Counter, b: Counter) -> float:
    if not a and not b:
        return 1.0
    inter = sum((a & b).values())
    union = sum((a | b).values())
    return inter / union if union else 0.0


def get_canonical_skill_name(skill_name: str) -> str:
    names = load_skills_database()
    if not names:
        return ""
    query = normalize_text_for_match(skill_name)
    qlen = len(query)
    qbigrams = build_bigrams(query)
    qtokens = set(query.split())

    index_cache = getattr(get_canonical_skill_name, 'cacheIndex', None)
    source_cache = getattr(get_canonical_skill_name, 'cacheSource', None)
    if index_cache is None or source_cache is not names:
        cache_list = []
        token_index = {}
        norm_map = {}
        for original in names:
            normalized = normalize_text_for_match(original)
            tokens = set(normalized.split())
            entry = (original, normalized, len(normalized), build_bigrams(normalized), tokens)
            cache_list.append(entry)
            norm_map[normalized] = original
            idx = len(cache_list) - 1
            for tok in tokens:
                if tok:
                    token_index.setdefault(tok, []).append(idx)
        setattr(get_canonical_skill_name, 'cacheIndex', cache_list)
        setattr(get_canonical_skill_name, 'cacheSource', names)
        setattr(get_canonical_skill_name, 'cacheTokenIndex', token_index)
        setattr(get_canonical_skill_name, 'cacheNormMap', norm_map)
        index_cache = cache_list

    best_key = None
    best_score = 0.0
    best_len_ratio = 0.0
    token_index = getattr(get_canonical_skill_name, 'cacheTokenIndex', None)
    candidate_indices = set()
    for tok in qtokens:
        if token_index and tok in token_index:
            for idx in token_index[tok]:
                candidate_indices.add(idx)
    iterable = candidate_indices or range(len(index_cache))
    for idx in iterable:
        original_key, normalized_key, normalized_length, normalized_bigrams, normalized_tokens = index_cache[idx]
        if not query or not normalized_key:
            continue
        if query in normalized_key or normalized_key in query:
            best_key = original_key
            best_score = 1.0
            best_len_ratio = min(qlen, normalized_length) / max(qlen, normalized_length) if max(qlen, normalized_length) else 1.0
            break
        token_inter = len(qtokens & normalized_tokens)
        token_union = len(qtokens | normalized_tokens) or 1
        token_score = token_inter / token_union
        bigram_score = jaccard_counter_ratio(qbigrams, normalized_bigrams)
        if normalized_length == qlen:
            positional = sum(1 for i in range(qlen) if query[i] == normalized_key[i]) / qlen if qlen else 0.0
            score = max(bigram_score, token_score, positional)
            len_ratio = 1.0
        else:
            score = max(bigram_score, token_score)
            len_ratio = min(qlen, normalized_length) / max(qlen, normalized_length)
        if score > best_score or (score == best_score and len_ratio > best_len_ratio):
            best_score = score
            best_len_ratio = len_ratio
            best_key = original_key

    if best_key is not None and ((best_score >= 0.85 and best_len_ratio >= 0.8) or best_score >= 0.95):
        return best_key
    return ""


def ocr_en(sub_img):
    return ocr_line(sub_img, lang="en")


def try_alt_cost_regions(skill_info_img):
    regions = [
        skill_info_img[65: 95, 520: 595],
        skill_info_img[70: 100, 515: 590],
        skill_info_img[60: 90, 530: 600],
    ]
    for i, alt_region in enumerate(regions):
        try:
            alt_cost_text = ocr_en(alt_region)
            alt_cost = re.sub("\\D", "", alt_cost_text)
            if alt_cost and alt_cost != '':
                return alt_cost, i+1
        except:
            continue
    return "", 0


def get_skill_list(img, skill: list[str], skill_blacklist: list[str]) -> list:
    origin_img = img
    img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    res = []
    while True:
        all_skill_scanned = True
        match_result = image_match(img, REF_SKILL_LIST_DETECT_LABEL)
        if match_result.find_match:
            all_skill_scanned = False
            pos = match_result.matched_area
            pos_center = match_result.center_point
            if 460 < pos_center[0] < 560 and 450 < pos_center[1] < 1050:
                skill_info_img = img[pos[0][1] - 65:pos[1][1] + 75, pos[0][0] - 470: pos[1][0] + 150]
                skill_info_cp = origin_img[pos[0][1] - 65:pos[1][1] + 75, pos[0][0] - 470: pos[1][0] + 150]

                skill_name_img = skill_info_img[10: 47, 100: 445]
                skill_cost_img = skill_info_img[69: 99, 525: 588]
                detected_text = ocr_en(skill_name_img)
                cost_text = ocr_en(skill_cost_img)
                cost = re.sub("\\D", "", cost_text)
                
                # Handle empty cost (Global Server UI compatibility)
                if not cost or cost == '':
                    alt_cost, alt_idx = try_alt_cost_regions(skill_info_img)
                    if alt_cost:
                        cost = alt_cost
                        log.debug(f"Found skill cost using alternative region {alt_idx}: '{alt_cost}' for '{detected_text}'")
                    if not cost or cost == '':
                        log.debug(f"Could not parse skill cost for '{detected_text}', cost_text: '{cost_text}', defaulting to 1")
                        cost = '1'

                # Check if it's a gold skill
                mask = cv2.inRange(skill_info_cp, numpy.array([40, 180, 240]), numpy.array([100, 210, 255]))
                is_gold = True if mask[120, 600] == 255 else False

                skill_in_priority_list = False
                skill_name_raw = "" # Save original skill name to prevent OCR deviation
                priority = 99
                matched_skill = get_canonical_skill_name(detected_text)
                name_for_match = matched_skill if matched_skill != "" else detected_text
                hint_level = 0
                try:
                    buy_x = pos_center[0] + 128
                    buy_y = pos_center[1]
                    probe_x = buy_x
                    probe_y = buy_y - 46
                    h0, w0 = origin_img.shape[:2]
                    if 0 <= probe_x < w0 and 0 <= probe_y < h0:
                        b, g, r = origin_img[probe_y, probe_x]
                        log.debug(f"hint rgb probe at ({probe_x},{probe_y}) bgr=({int(b)},{int(g)},{int(r)})")
                        if abs(int(r) - 255) <= 8 and abs(int(g) - 145) <= 8 and abs(int(b) - 28) <= 8:
                            rx1, ry1 = buy_x - 62, buy_y - 71
                            rx2, ry2 = buy_x - 6, buy_y - 50
                            rx1 = max(0, min(w0, rx1)); rx2 = max(rx1, min(w0, rx2))
                            ry1 = max(0, min(h0, ry1)); ry2 = max(ry1, min(h0, ry2))
                            roi = origin_img[ry1:ry2, rx1:rx2]
                            if roi is not None and getattr(roi, 'size', 0) > 0:
                                roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
                                lvl = 0
                                for i, tpl in enumerate(REF_HINT_LEVELS):
                                    try:
                                        mr = image_match(roi_gray, tpl)
                                        log.debug(f"hint tpl L{i+1} match={mr.find_match}")
                                        if mr.find_match:
                                            lvl = i + 1
                                            break
                                    except Exception:
                                        continue
                                hint_level = lvl
                except Exception as e:
                    log.debug(f"hint level error: {e}")
                log.info(f"detected text='{detected_text}' matched skill='{matched_skill}' Hint: lv {hint_level}")
                normalized_name = normalize_text_for_match(name_for_match)
                in_blacklist = any(normalized_name == normalize_text_for_match(b) for b in skill_blacklist)
                
                if in_blacklist:
                    priority = -1
                    skill_name_raw = name_for_match
                    skill_in_priority_list = True
                else:
                    for i in range(len(skill)):
                        if any(normalized_name == normalize_text_for_match(s) for s in skill[i]):
                            priority = i
                            skill_name_raw = name_for_match
                            skill_in_priority_list = True
                            break
                if not skill_in_priority_list:
                    priority = len(skill)

                available = not image_match(skill_info_img, REF_SKILL_LEARNED).find_match

                if priority != -1: # Exclude skills that appear in blacklist
                    res.append({"skill_name": detected_text,
                                "skill_name_raw": skill_name_raw,
                                "skill_cost": int(cost),
                                "priority": priority,
                                "gold": is_gold,
                                "subsequent_skill": "",
                                "available": available,
                                "hint_level": int(hint_level),
                                "y_pos": int(pos_center[1])})
            img[match_result.matched_area[0][1]:match_result.matched_area[1][1],
                match_result.matched_area[0][0]:match_result.matched_area[1][0]] = 0

        # Parse previously obtained skills
        match_result = image_match(img, REF_SKILL_LEARNED)
        if match_result.find_match:
            all_skill_scanned = False
            pos = match_result.matched_area
            pos_center = match_result.center_point
            if 550 < pos_center[0] < 640 and 450 < pos_center[1] < 1050:
                skill_info_img = img[pos[0][1] - 65:pos[1][1] + 75, pos[0][0] - 520: pos[1][0] + 150]
                skill_info_cp = origin_img[pos[0][1] - 65:pos[1][1] + 75, pos[0][0] - 470: pos[1][0] + 150]

                # Check if it's a gold skill
                mask = cv2.inRange(skill_info_cp, numpy.array([40, 180, 240]), numpy.array([100, 210, 255]))
                is_gold = True if mask[120, 600] == 255 else False
                skill_name_img = skill_info_img[10: 47, 100: 445]
                detected_text = ocr_line(skill_name_img)
                res.append({"skill_name": detected_text,
                            "skill_name_raw": detected_text,
                            "skill_cost": 0,
                            "priority": -1,
                            "gold": is_gold,
                            "subsequent_skill": "",
                            "available": False,
                            "y_pos": int(pos_center[1])})
            img[match_result.matched_area[0][1]:match_result.matched_area[1][1],
                match_result.matched_area[0][0]:match_result.matched_area[1][0]] = 0
        if all_skill_scanned:
            break

    res = sorted(res, key=lambda x: x["y_pos"])
    # No precise calculation, but approximately y-axis less than 540 will cause skill name to display incompletely. No problems tested yet.
    return [{k: v for k, v in r.items() if k != "y_pos"} for r in res if r["y_pos"] >= 540]


def find_skill(ctx, img, skill: list[str], learn_any_skill: bool) -> bool:
    log.debug(f"🔍 find_skill called with {len(skill)} skills: {skill}")
    img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    find = False
    while True:
        match_result = image_match(img, REF_SKILL_LIST_DETECT_LABEL)
        if match_result.find_match:
            pos = match_result.matched_area
            pos_center = match_result.center_point
            if 460 < pos_center[0] < 560 and 450 < pos_center[1] < 1050:
                skill_info_img = img[pos[0][1] - 65:pos[1][1] + 75, pos[0][0] - 470: pos[1][0] + 150]
                if not image_match(skill_info_img, REF_SKILL_LEARNED).find_match:
                    skill_name_img = skill_info_img[10: 47, 100: 445]
                    detected_text = ocr_en(skill_name_img)
                    matched_skill = get_canonical_skill_name(detected_text)
                    name_for_match = matched_skill if matched_skill != "" else detected_text
                    hint_level = 0
                    try:
                        origin_img = ctx.ctrl.get_screen()
                        buy_x = match_result.center_point[0] + 128
                        buy_y = match_result.center_point[1]
                        probe_x = buy_x
                        probe_y = buy_y - 46
                        h0, w0 = origin_img.shape[:2]
                        if 0 <= probe_x < w0 and 0 <= probe_y < h0:
                            b, g, r = origin_img[probe_y, probe_x]
                            log.debug(f"hint rgb probe at ({probe_x},{probe_y}) bgr=({int(b)},{int(g)},{int(r)})")
                            if abs(int(r) - 255) <= 8 and abs(int(g) - 145) <= 8 and abs(int(b) - 28) <= 8:
                                rx1, ry1 = buy_x - 62, buy_y - 71
                                rx2, ry2 = buy_x - 6, buy_y - 50
                                rx1 = max(0, min(w0, rx1)); rx2 = max(rx1, min(w0, rx2))
                                ry1 = max(0, min(h0, ry1)); ry2 = max(ry1, min(h0, ry2))
                                roi = origin_img[ry1:ry2, rx1:rx2]
                                if roi is not None and getattr(roi, 'size', 0) > 0:
                                    roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
                                    best_lvl = 0
                                    best_score = 0.0
                                    for i, tpl in enumerate(REF_HINT_LEVELS):
                                        try:
                                            mr = image_match(roi_gray, tpl)
                                            log.debug(f"hint tpl L{i+1} match={mr.find_match} score={getattr(mr,'score',0)}")
                                            if mr.find_match and getattr(mr, 'score', 0) > best_score:
                                                best_score = float(getattr(mr, 'score', 0))
                                                best_lvl = i + 1
                                        except Exception:
                                            continue
                                    hint_level = best_lvl
                    except Exception as e:
                        log.debug(f"hint level error: {e}")
                    log.info(f"detected text='{detected_text}' matched skill='{matched_skill}'")
                    target_match = None
                    for target in skill:
                        if (normalize_text_for_match(name_for_match) == normalize_text_for_match(target)
                            or normalize_text_for_match(detected_text) == normalize_text_for_match(target)):
                            target_match = target
                            break
                    
                    if target_match is not None or learn_any_skill:
                        tmp_img = ctx.ctrl.get_screen()
                        pt_text = re.sub("\\D", "", ocr_en(tmp_img[400: 440, 490: 665]))
                        skill_pt_cost_text = re.sub("\\D", "", ocr_en(skill_info_img[69: 99, 525: 588]))
                        
                        # Handle empty cost (Global Server UI compatibility) - same as get_skill_list()
                        if not skill_pt_cost_text or skill_pt_cost_text == '':
                            alt_cost, alt_idx = try_alt_cost_regions(skill_info_img)
                            if alt_cost:
                                skill_pt_cost_text = alt_cost
                                log.debug(f"find_skill - Found skill cost using alternative region {alt_idx}: '{alt_cost}' for '{detected_text}'")
                            if not skill_pt_cost_text or skill_pt_cost_text == '':
                                log.debug(f"find_skill - Could not parse skill cost for '{detected_text}', defaulting to 1")
                                skill_pt_cost_text = '1'
                        
                        # Debug: Log point and cost extraction
                        log.debug(f"🔍 find_skill - Available points: '{pt_text}', Skill cost: '{skill_pt_cost_text}'")
                        
                        if pt_text != "" and skill_pt_cost_text != "":
                            pt = int(pt_text)
                            skill_pt_cost = int(skill_pt_cost_text)
                            log.debug(f"🔍 find_skill - Points: {pt}, Cost: {skill_pt_cost}, Can buy: {pt >= skill_pt_cost}")
                            
                            if pt >= skill_pt_cost:
                                log.info(f"✅ Buying skill '{detected_text}' - Points: {pt}, Cost: {skill_pt_cost}")
                                ctx.ctrl.click(match_result.center_point[0] + 128, match_result.center_point[1],
                                               "Bonus Skills：" + detected_text)
                                if target_match is not None and target_match in skill:
                                    skill.remove(target_match)
                                    log.info(f"✅ Removed '{target_match}' from skill list. Remaining: {skill}")
                                elif target_match is not None:
                                    log.warning(f"⚠️ Skill '{target_match}' not found in skill list: {skill}")
                                ctx.career.learn_skill_selected = True
                                find = True
                            else:
                                log.debug(f"❌ Not enough points for '{detected_text}' - Need {skill_pt_cost}, have {pt}")
                        else:
                            log.debug(f"❌ Failed to extract points/cost - Points: '{pt_text}', Cost: '{skill_pt_cost_text}'")

            img[match_result.matched_area[0][1]:match_result.matched_area[1][1],
            match_result.matched_area[0][0]:match_result.matched_area[1][0]] = 0

        else:
            break
    return find
