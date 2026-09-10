"""Reading things off the screen that no template can match.

Everything here is copied from the parent project rather than rewritten. The
constants are pixel geometry measured against the live game at 720x1280, and
the colour thresholds were tuned against real frames; both are calibration, and
calibration gets moved, not redrawn.
"""
import re
import time
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
