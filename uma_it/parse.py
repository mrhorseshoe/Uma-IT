"""Reading things off the screen that no template can match.

Everything here is copied from the parent project rather than rewritten. The
constants are pixel geometry measured against the live game at 720x1280, and
the colour thresholds were tuned against real frames; both are calibration, and
calibration gets moved, not redrawn.
"""
import re

import cv2
import numpy

from bot.recog.ocr import ocr_line

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
