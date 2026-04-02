from __future__ import annotations

import html
import re
from datetime import date, datetime


def parse_time_mmss(value):
    if value is None:
        return None

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        total_seconds = int(float(value))
        return max(0, total_seconds)

    raw = str(value).strip()
    if not raw:
        return None

    if ":" in raw:
        parts = raw.split(":")
        if len(parts) != 2:
            return None
        minutes_raw, seconds_raw = parts
        if not minutes_raw.isdigit() or not seconds_raw.isdigit():
            return None
        minutes = int(minutes_raw)
        seconds = int(seconds_raw)
        if seconds < 0 or seconds > 59:
            return None
        return minutes * 60 + seconds

    digits = re.sub(r"\D", "", raw)
    if not digits:
        return None

    if len(digits) <= 2:
        minutes = 0
        seconds = int(digits)
    else:
        minutes = int(digits[:-2])
        seconds = int(digits[-2:])

    if seconds > 59:
        return None
    return minutes * 60 + seconds


def format_time_mmss(value) -> str:
    total_seconds = parse_time_mmss(value)
    if total_seconds is None:
        return ""
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes}:{seconds:02d}"


def display_result_value(score: dict, value) -> str:
    if value is None or value == "":
        return ""

    score_type = score.get("type")

    if score_type == "time":
        pretty = format_time_mmss(value)
        return pretty or str(value)

    if score_type == "weight":
        try:
            num = float(value)
            if num.is_integer():
                return str(int(num))
            return str(num)
        except (TypeError, ValueError):
            return str(value)

    if score_type == "reps":
        try:
            num = float(value)
            if num.is_integer():
                return str(int(num))
            return str(num)
        except (TypeError, ValueError):
            return str(value)

    return str(value)


def compact_page_style() -> None:
    import streamlit as st

    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 0.8rem;
            padding-bottom: 1.2rem;
            max-width: 1500px;
        }
        h1, h2, h3 { line-height: 1.25 !important; overflow: visible !important; white-space: normal !important; }
        h1 { font-size: 1.55rem !important; margin-bottom: 0.4rem !important; }
        h2 { font-size: 1.2rem !important; margin-bottom: 0.3rem !important; }
        h3 { font-size: 1.0rem !important; margin-bottom: 0.2rem !important; }
        [data-testid="stSidebarNav"] a, [data-testid="stSidebarNav"] a * { white-space: normal !important; overflow: visible !important; text-overflow: unset !important; line-height: 1.2 !important; }
        p, li, label, .stCaption, .stMarkdown, .stTextInput, .stSelectbox, .stNumberInput {
            font-size: 0.92rem !important;
        }
        div[data-testid="stVerticalBlock"] > div:has(> div[data-testid="stHorizontalBlock"]) {
            gap: 0.45rem;
        }
        div[data-testid="stHorizontalBlock"] {
            gap: 0.45rem;
        }
        .stButton > button, .stDownloadButton > button {
            padding-top: 0.35rem !important;
            padding-bottom: 0.35rem !important;
        }
        div[data-testid="stDataFrame"] table { font-size: 0.88rem !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def escape_html(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def parse_birth_date(value):
    if isinstance(value, date):
        return value
    raw = "" if value is None else str(value).strip()
    if not raw:
        return None

    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def birth_date_to_storage(value) -> str:
    parsed = parse_birth_date(value)
    return parsed.isoformat() if parsed else ""


def display_birth_date(value) -> str:
    parsed = parse_birth_date(value)
    return parsed.strftime("%d.%m.%Y") if parsed else ""


def calculate_age(birth_date_value, on_date=None):
    born = parse_birth_date(birth_date_value)
    if not born:
        return None
    ref = on_date or date.today()
    if isinstance(ref, datetime):
        ref = ref.date()
    years = ref.year - born.year
    if (ref.month, ref.day) < (born.month, born.day):
        years -= 1
    return max(0, years)


def participant_age(participant: dict, on_date=None):
    age = calculate_age(participant.get("birth_date"), on_date=on_date)
    if age is not None:
        return age

    raw_age = participant.get("age", "")
    if raw_age in (None, ""):
        return ""
    try:
        return int(raw_age)
    except (TypeError, ValueError):
        return raw_age
