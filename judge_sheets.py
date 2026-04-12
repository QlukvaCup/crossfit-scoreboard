from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from config import DIVISIONS

PAGE_W, PAGE_H = A4
MARGIN_X = 15 * mm
TOP_Y = PAGE_H - 22 * mm

_FONT_REGULAR = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"
_FONTS_READY = False


@dataclass
class JudgeSheetRow:
    athlete_id: int
    athlete_name: str
    athlete_meta: str
    division_id: str
    division_title: str
    heat_no: int
    lane_no: int
    wod_id: str


DIVISION_TITLE_MAP = {d["id"]: d["title"] for d in DIVISIONS}
DIVISION_SHEET_TITLE = {
    "BEGSCAL_M": "Beginners / Scaled — МУЖЧИНЫ",
    "BEGSCAL_F": "Beginners / Scaled — ЖЕНЩИНЫ",
    "INT_M": "Intermediate — МУЖЧИНЫ",
    "INT_F": "Intermediate — ЖЕНЩИНЫ",
}

WOD1_STAGES = {
    "INT_M": [
        ("рывок", "15", "15"),
        ("дв ск-ки", "60", "75"),
        ("взятие+толчок", "20", "95"),
        ("дв ск-ки", "60", "155"),
        ("фр. приседания", "25", "180"),
        ("дв ск-ки", "60", "240"),
    ],
    "INT_F": [
        ("рывок", "15", "15"),
        ("дв ск-ки", "60", "75"),
        ("взятие+толчок", "20", "95"),
        ("дв ск-ки", "60", "155"),
        ("фр. приседания", "25", "180"),
        ("дв ск-ки", "60", "240"),
    ],
    "BEGSCAL_M": [
        ("рывок", "15", "15"),
        ("ск-ка", "120", "135"),
        ("взятие+толчок", "20", "155"),
        ("ск-ка", "120", "275"),
        ("фр. приседания", "25", "300"),
        ("ск-ка", "120", "420"),
    ],
    "BEGSCAL_F": [
        ("рывок", "15", "15"),
        ("ск-ка", "120", "135"),
        ("взятие+толчок", "20", "155"),
        ("ск-ка", "120", "275"),
        ("фр. приседания", "25", "300"),
        ("ск-ка", "120", "420"),
    ],
}

WOD3_STAGES = {
    "INT_M": [
        ("гребля", "20", "20"),
        ("берпи ч/з бокс", "15", "35"),
        ("выпады 30 м", "6", "41"),
        ("ферм. прогулка 50 м", "10", "51"),
        ("челночный бег 70 м", "14", "65"),
        ("берпи ч/з бокс", "15", "80"),
        ("гребля", "20", "100"),
    ],
    "INT_F": [
        ("гребля", "16", "16"),
        ("берпи ч/з бокс", "15", "31"),
        ("выпады 30 м", "6", "37"),
        ("ферм. прогулка 50 м", "10", "47"),
        ("челночный бег 70 м", "14", "61"),
        ("берпи ч/з бокс", "15", "76"),
        ("гребля", "16", "92"),
    ],
    "BEGSCAL_M": [
        ("гребля", "16", "16"),
        ("берпи ч/з бокс", "15", "31"),
        ("выпады 30 м", "6", "37"),
        ("ферм. прогулка 50 м", "10", "47"),
        ("челночный бег 70 м", "14", "61"),
        ("берпи ч/з бокс", "15", "76"),
        ("гребля", "16", "92"),
    ],
    "BEGSCAL_F": [
        ("гребля", "12", "12"),
        ("берпи ч/з бокс", "15", "27"),
        ("выпады 30 м", "6", "33"),
        ("ферм. прогулка 50 м", "10", "43"),
        ("челночный бег 70 м", "14", "57"),
        ("берпи ч/з бокс", "15", "72"),
        ("гребля", "12", "84"),
    ],
}

WOD_INFO = {
    "WOD1": {"title": "Комплекс 1", "format": "FOR TIME", "cap": "8 min"},
    "WOD2": {"title": "Комплекс 2", "format": "AMRAP + STRENGTH", "cap": "5+4 мин"},
    "WOD3": {"title": "Комплекс 3", "format": "FOR TIME", "cap": "9 min"},
}


# ---------- fonts ----------
def _try_register_font(font_name: str, candidates: Iterable[str]) -> bool:
    for path in candidates:
        p = Path(path)
        if p.exists():
            pdfmetrics.registerFont(TTFont(font_name, str(p)))
            return True
    return False


def _ensure_fonts() -> None:
    global _FONTS_READY, _FONT_REGULAR, _FONT_BOLD
    if _FONTS_READY:
        return
    reg_ok = _try_register_font(
        "JudgeRegular",
        [r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\DejaVuSans.ttf", r"C:\Windows\Fonts\calibri.ttf"],
    )
    bold_ok = _try_register_font(
        "JudgeBold",
        [r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\DejaVuSans-Bold.ttf", r"C:\Windows\Fonts\calibrib.ttf"],
    )
    if reg_ok:
        _FONT_REGULAR = "JudgeRegular"
    if bold_ok:
        _FONT_BOLD = "JudgeBold"
    else:
        _FONT_BOLD = _FONT_REGULAR
    _FONTS_READY = True


def _font(bold: bool = False) -> str:
    return _FONT_BOLD if bold else _FONT_REGULAR


# ---------- public api ----------
def participant_map(db: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    result: Dict[int, Dict[str, Any]] = {}
    for item in db.get("participants", []):
        if item.get("deleted", False):
            continue
        try:
            result[int(item.get("id"))] = item
        except (TypeError, ValueError):
            continue
    return result


def selected_divisions(db: Dict[str, Any], wod_id: str, division_ids: Sequence[str]) -> List[str]:
    heats = db.get("heats", {}).get(wod_id, {})
    return [div for div in division_ids if heats.get(div)]


def count_rows_by_division(db: Dict[str, Any], wod_id: str, divisions: Sequence[str]) -> List[Dict[str, Any]]:
    rows = collect_judge_sheet_rows(db, wod_id, divisions)
    counts: Dict[str, int] = {div: 0 for div in divisions}
    for row in rows:
        counts[row.division_id] = counts.get(row.division_id, 0) + 1
    return [
        {
            "division": div,
            "division_title": DIVISION_TITLE_MAP.get(div, div),
            "count": counts.get(div, 0),
        }
        for div in divisions
    ]


def collect_judge_sheet_rows(db: Dict[str, Any], wod_id: str, division_ids: Sequence[str]) -> List[JudgeSheetRow]:
    heats = db.get("heats", {}).get(wod_id, {})
    athletes = participant_map(db)
    rows: List[JudgeSheetRow] = []

    for division_id in division_ids:
        division_heats = heats.get(division_id) or []
        for heat in sorted(division_heats, key=lambda x: int(x.get("heat") or x.get("heat_no") or 0)):
            heat_no = int(heat.get("heat") or heat.get("heat_no") or 0)
            assignments = sorted(heat.get("assignments") or [], key=lambda x: int(x.get("lane") or 0))
            for assignment in assignments:
                athlete_id_raw = assignment.get("athlete_id")
                if athlete_id_raw in (None, ""):
                    continue
                try:
                    athlete_id = int(athlete_id_raw)
                    lane_no = int(assignment.get("lane") or 0)
                except (TypeError, ValueError):
                    continue
                athlete = athletes.get(athlete_id)
                if not athlete:
                    continue
                meta_parts = []
                for key in ("city", "region", "club"):
                    value = str(athlete.get(key) or "").strip()
                    if value:
                        meta_parts.append(value)
                rows.append(
                    JudgeSheetRow(
                        athlete_id=athlete_id,
                        athlete_name=str(athlete.get("full_name") or f"ID {athlete_id}"),
                        athlete_meta=" · ".join(meta_parts),
                        division_id=division_id,
                        division_title=DIVISION_SHEET_TITLE.get(division_id, DIVISION_TITLE_MAP.get(division_id, division_id)),
                        heat_no=heat_no,
                        lane_no=lane_no,
                        wod_id=wod_id,
                    )
                )
    rows.sort(key=lambda x: (x.division_title, x.heat_no, x.lane_no, x.athlete_name.casefold()))
    return rows


def build_judge_sheets_pdf_bytes(db: Dict[str, Any], wod_id: str, division_ids: Sequence[str]) -> bytes:
    _ensure_fonts()
    rows = collect_judge_sheet_rows(db, wod_id, division_ids)
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    if not rows:
        _draw_empty(c, wod_id)
        c.save()
        return buf.getvalue()

    for row in rows:
        if wod_id == "WOD1":
            _draw_wod1(c, row)
        elif wod_id == "WOD2":
            _draw_wod2(c, row)
        else:
            _draw_wod3(c, row)
        c.showPage()
    c.save()
    return buf.getvalue()


# ---------- drawing helpers ----------
def _text(c: canvas.Canvas, x: float, y: float, text: str, size: int = 10, bold: bool = False):
    c.setFont(_font(bold), size)
    c.drawString(x, y, text)


def _fit_text(c: canvas.Canvas, x: float, y: float, width: float, text: str, size: int = 10, bold: bool = False, min_size: int = 7):
    font_name = _font(bold)
    current = size
    while current >= min_size and pdfmetrics.stringWidth(text, font_name, current) > width:
        current -= 0.5
    c.setFont(font_name, current)
    c.drawString(x, y, text)


def _center(c: canvas.Canvas, x: float, y: float, width: float, text: str, size: int = 10, bold: bool = False):
    c.setFont(_font(bold), size)
    c.drawCentredString(x + width / 2, y, text)


def _box(c: canvas.Canvas, x: float, y: float, w: float, h: float, fill: int = 0):
    c.rect(x, y, w, h, stroke=1, fill=fill)


def _line(c: canvas.Canvas, x1: float, y1: float, x2: float, y2: float):
    c.line(x1, y1, x2, y2)


def _checkbox(c: canvas.Canvas, x: float, y: float, s: float = 5 * mm):
    _box(c, x, y, s, s)


def _draw_page_frame(c: canvas.Canvas):
    _box(c, 10 * mm, 10 * mm, PAGE_W - 20 * mm, PAGE_H - 20 * mm)


def _draw_title(c: canvas.Canvas, wod_id: str):
    info = WOD_INFO[wod_id]
    # lowered title block
    c.setLineWidth(1)
    _center(c, 0, PAGE_H - 24 * mm, PAGE_W, "QLUKVA CUP", 16, True)
    _center(c, 0, PAGE_H - 36 * mm, PAGE_W, f"{info['title']} — Судейский бланк", 12, True)


def _draw_header_grid(c: canvas.Canvas, row: JudgeSheetRow, wod_id: str):
    info = WOD_INFO[wod_id]
    x = 15 * mm
    y = PAGE_H - 68 * mm
    w = PAGE_W - 30 * mm
    h = 28 * mm
    _box(c, x, y, w, h)

    # vertical splits
    col1 = 94 * mm
    col2 = 46 * mm
    _line(c, x + col1, y, x + col1, y + h)
    _line(c, x + col1 + col2, y, x + col1 + col2, y + h)
    _line(c, x, y + h/2, x + w, y + h/2)

    _text(c, x + 4 * mm, y + h - 8 * mm, "Категория:", 10, True)
    _fit_text(c, x + 24 * mm, y + h - 8 * mm, col1 - 28 * mm, row.division_title, 10)

    _text(c, x + col1 + 4 * mm, y + h - 8 * mm, "Заход:", 10, True)
    _text(c, x + col1 + 26 * mm, y + h - 8 * mm, str(row.heat_no), 10)

    _text(c, x + col1 + col2 + 4 * mm, y + h - 8 * mm, "Дорожка:", 10, True)
    _text(c, x + col1 + col2 + 28 * mm, y + h - 8 * mm, str(row.lane_no), 10)

    _text(c, x + 4 * mm, y + 8 * mm, "Атлет:", 10, True)
    _fit_text(c, x + 21 * mm, y + 8 * mm, col1 - 25 * mm, row.athlete_name, 12, True)

    # moved format left and made fit
    _text(c, x + col1 + 4 * mm, y + 8 * mm, "Формат:", 10, True)
    _fit_text(c, x + col1 + 27 * mm, y + 8 * mm, col2 - 30 * mm + 20 * mm, info["format"], 9)

    _text(c, x + col1 + col2 + 4 * mm, y + 8 * mm, "Лимит:", 10, True)
    _text(c, x + col1 + col2 + 24 * mm, y + 8 * mm, info["cap"], 10)

    if row.athlete_meta:
        _fit_text(c, x + 21 * mm, y - 3 * mm, w - 24 * mm, row.athlete_meta, 8)


def _draw_footer(c: canvas.Canvas, wod_id: str):
    x = 15 * mm
    w = PAGE_W - 30 * mm
    y = 18 * mm
    h = 16 * mm
    _box(c, x, y, w, h)
    parts = [35 * mm, 40 * mm, 35 * mm]
    cur = x + parts[0]
    _line(c, cur, y, cur, y + h)
    cur += parts[1]
    _line(c, cur, y, cur, y + h)
    cur += parts[2]
    _line(c, cur, y, cur, y + h)
    _line(c, x, y + h/2, x + w, y + h/2)

    _text(c, x + 2 * mm, y + h - 5 * mm, "Судья", 9, True)
    _text(c, x + parts[0] + 2 * mm, y + h - 5 * mm, "Итоговый результат", 9, True)
    _text(c, x + parts[0] + parts[1] + 2 * mm, y + h - 5 * mm, "Статус", 9, True)
    _text(c, x + parts[0] + parts[1] + parts[2] + 2 * mm, y + h - 5 * mm, "Время / reps", 9, True)


def _draw_notes(c: canvas.Canvas, y_top: float, height: float = 30 * mm):
    x = 15 * mm
    w = PAGE_W - 30 * mm
    _text(c, x + 2 * mm, y_top + 2 * mm, "Заметки судьи", 10, True)
    _box(c, x, y_top - height, w, height)


def _draw_empty(c: canvas.Canvas, wod_id: str):
    _draw_page_frame(c)
    _draw_title(c, wod_id)
    _center(c, 0, PAGE_H / 2, PAGE_W, "Нет назначенных heats для выбранных категорий", 14, True)


# ---------- WOD1 ----------
def _draw_wod1(c: canvas.Canvas, row: JudgeSheetRow):
    _draw_page_frame(c)
    _draw_title(c, "WOD1")
    _draw_header_grid(c, row, "WOD1")

    stages = WOD1_STAGES[row.division_id]
    x = 15 * mm
    y_top = PAGE_H - 112 * mm
    w = PAGE_W - 30 * mm
    h = 74 * mm
    _box(c, x, y_top - h, w, h)
    _text(c, x + 3 * mm, y_top - 7 * mm, "Контроль выполнения", 10, True)

    table_y = y_top - 16 * mm
    row_h = 8 * mm
    cols = [10 * mm, 45 * mm, 20 * mm, 14 * mm, 22 * mm, w - (10+45+20+14+22) * mm]
    cur = x
    for cw in cols[:-1]:
        cur += cw
        _line(c, cur, table_y - 6 * row_h, cur, table_y)
    for i in range(7):
        _line(c, x, table_y - i * row_h, x + w, table_y - i * row_h)

    headers = ["#", "Движение", "Кол-во", "✓", "Сумма", "Прим."]
    cur = x
    for head, cw in zip(headers, cols):
        _text(c, cur + 2 * mm, table_y - 5 * mm, head, 9, True)
        cur += cw

    y = table_y - row_h
    for idx, (name, qty, total) in enumerate(stages, start=1):
        _text(c, x + 2 * mm, y - 5 * mm, str(idx), 9)
        _fit_text(c, x + cols[0] + 2 * mm, y - 5 * mm, cols[1] - 4 * mm, name, 9)
        _text(c, x + cols[0] + cols[1] + 2 * mm, y - 5 * mm, qty, 9)
        _checkbox(c, x + cols[0] + cols[1] + cols[2] + 4 * mm, y - 6.2 * mm, 5 * mm)
        _text(c, x + cols[0] + cols[1] + cols[2] + cols[3] + 2 * mm, y - 5 * mm, total, 9, True)
        y -= row_h

    _draw_notes(c, 78 * mm)
    _draw_footer(c, "WOD1")


# ---------- WOD2 ----------
def _wod2_rounds(division_id: str) -> List[Dict[str, str]]:
    if division_id.startswith("INT"):
        start_pull = 5
        max_rounds = 10
    elif division_id == "BEGSCAL_M":
        start_pull = 4
        max_rounds = 10
    else:
        start_pull = 3
        max_rounds = 10
    rows = []
    total = 0
    for rnd in range(1, max_rounds + 1):
        devil = 2
        pull = start_pull + rnd - 1
        total += devil + pull + devil + pull
        rows.append({
            "rnd": str(rnd),
            "d1": str(devil),
            "pull": str(pull),
            "d2": str(devil),
            "core": str(pull),
            "sum": str(total),
        })
    return rows


def _wod2_pull_label(division_id: str) -> str:
    return "НКП" if division_id.startswith("INT") else "под.ия"


def _draw_wod2(c: canvas.Canvas, row: JudgeSheetRow):
    _draw_page_frame(c)
    _draw_title(c, "WOD2")
    _draw_header_grid(c, row, "WOD2")

    x = 15 * mm
    w = PAGE_W - 30 * mm
    y_top = PAGE_H - 112 * mm
    h = 102 * mm
    _box(c, x, y_top - h, w, h)
    _text(c, x + 3 * mm, y_top - 7 * mm, "Часть A — раунды", 10, True)

    table_y = y_top - 14 * mm
    row_h = 8 * mm
    pull_label = _wod2_pull_label(row.division_id)
    cols = [12 * mm, 20 * mm, 20 * mm, 20 * mm, 20 * mm, 16 * mm, 22 * mm, w - (12+20+20+20+20+16+22) * mm]
    cur = x
    for cw in cols[:-1]:
        cur += cw
        _line(c, cur, table_y - 10 * row_h, cur, table_y)
    for i in range(11):
        _line(c, x, table_y - i * row_h, x + w, table_y - i * row_h)
    headers = ["Rnd", "дьяв", pull_label, "дьяв", pull_label, "✓", "Сумма", "Прим."]
    cur = x
    for head, cw in zip(headers, cols):
        _fit_text(c, cur + 1.8 * mm, table_y - 5 * mm, cw - 3 * mm, head, 9, True)
        cur += cw

    rounds = _wod2_rounds(row.division_id)
    y = table_y - row_h
    for r in rounds:
        values = [r["rnd"], r["d1"], r["pull"], r["d2"], r["core"]]
        cur_x = x
        for val, cw in zip(values, cols[:5]):
            _text(c, cur_x + 2 * mm, y - 5 * mm, val, 9)
            cur_x += cw
        _checkbox(c, x + sum(cols[:5]) + 4 * mm, y - 6.2 * mm, 5 * mm)
        _text(c, x + sum(cols[:6]) + 2 * mm, y - 5 * mm, r["sum"], 9, True)
        y -= row_h

    # Part B
    part_b_y = y_top - 14 * mm - 10 * row_h - 10 * mm
    _text(c, x + 3 * mm, part_b_y, "Часть B — max clean + hang clean", 10, True)
    ay = part_b_y - 6 * mm
    labels = ["Попытка 1", "Попытка 2", "Попытка 3", "Лучший вес"]
    for label in labels:
        _box(c, x + 3 * mm, ay - 6 * mm, 44 * mm, 8 * mm)
        _text(c, x + 5 * mm, ay - 1 * mm, label, 9, True)
        _box(c, x + 47 * mm, ay - 6 * mm, 28 * mm, 8 * mm)
        ay -= 10 * mm

    _draw_footer(c, "WOD2")


# ---------- WOD3 ----------
def _draw_wod3(c: canvas.Canvas, row: JudgeSheetRow):
    _draw_page_frame(c)
    _draw_title(c, "WOD3")
    _draw_header_grid(c, row, "WOD3")

    stages = WOD3_STAGES[row.division_id]
    x = 15 * mm
    y_top = PAGE_H - 112 * mm
    w = PAGE_W - 30 * mm
    h = 84 * mm
    _box(c, x, y_top - h, w, h)
    _text(c, x + 3 * mm, y_top - 7 * mm, "Контроль выполнения", 10, True)

    table_y = y_top - 16 * mm
    row_h = 8 * mm
    cols = [10 * mm, 52 * mm, 17 * mm, 14 * mm, 22 * mm, w - (10+52+17+14+22) * mm]
    cur = x
    for cw in cols[:-1]:
        cur += cw
        _line(c, cur, table_y - 7 * row_h, cur, table_y)
    for i in range(8):
        _line(c, x, table_y - i * row_h, x + w, table_y - i * row_h)

    headers = ["#", "Движение", "Кол-во", "✓", "Сумма", "Прим."]
    cur = x
    for head, cw in zip(headers, cols):
        _text(c, cur + 2 * mm, table_y - 5 * mm, head, 9, True)
        cur += cw

    y = table_y - row_h
    for idx, (name, qty, total) in enumerate(stages, start=1):
        _text(c, x + 2 * mm, y - 5 * mm, str(idx), 9)
        _fit_text(c, x + cols[0] + 2 * mm, y - 5 * mm, cols[1] - 4 * mm, name, 9)
        _text(c, x + cols[0] + cols[1] + 2 * mm, y - 5 * mm, qty, 9)
        _checkbox(c, x + cols[0] + cols[1] + cols[2] + 4 * mm, y - 6.2 * mm, 5 * mm)
        _text(c, x + cols[0] + cols[1] + cols[2] + cols[3] + 2 * mm, y - 5 * mm, total, 9, True)
        y -= row_h

    _draw_notes(c, 68 * mm, 40 * mm)
    _draw_footer(c, "WOD3")
