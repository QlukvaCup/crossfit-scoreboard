import json
import os
from typing import Dict, Any, List

from config import DATA_DIR, DB_FILE, DATA_FLAGS_DIR, DIVISIONS, DEFAULT_SCORES
from utils import birth_date_to_storage


PODIUM_PLACES = (1, 2, 3)


def default_display_settings() -> Dict[str, Any]:
    return {
        "main": {
            "section_title_size": 18,
            "card_title_size": 16,
            "table_text_size": 11,
            "meta_text_size": 10,
            "row_height": 4,
            "block_gap": 8,
            "container_scale": 1.0,
        },
        "mobile": {
            "section_title_size": 22,
            "card_title_size": 18,
            "table_text_size": 12,
            "meta_text_size": 11,
            "row_height": 6,
            "block_gap": 12,
            "container_scale": 1.0,
        },
    }


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DATA_FLAGS_DIR.mkdir(parents=True, exist_ok=True)


def default_team_scoring() -> Dict[str, Any]:
    return {
        "enabled": True,
        "priority_score_id": "WOD3",
        "places": [1, 2, 3],
        "division_points": {
            "BEGSCAL_M": {"1": 7, "2": 5, "3": 3},
            "BEGSCAL_F": {"1": 7, "2": 5, "3": 3},
            "INT_M": {"1": 10, "2": 7, "3": 5},
            "INT_F": {"1": 10, "2": 7, "3": 5},
        },
    }


def default_db() -> Dict[str, Any]:
    return {
        "settings": {
            "division_limits": {
                "BEGSCAL_M": 16,
                "BEGSCAL_F": 8,
                "INT_M": 16,
                "INT_F": 8,
            },
            "scores": DEFAULT_SCORES,
            "display": default_display_settings(),
            "clubs": [],
            "team_scoring": default_team_scoring(),
            "tv_scene_duration_sec": 10,
        },
        "participants": [],
        "results": {},
        "heats": {},
        "meta": {
            "version": 6,
        },
    }


def _normalize_clubs(raw: Any) -> List[str]:
    items = raw if isinstance(raw, list) else []
    cleaned: List[str] = []
    seen = set()
    for item in items:
        name = str(item or "").strip()
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(name)
    cleaned.sort(key=lambda x: x.casefold())
    return cleaned


def _normalize_division_points(raw: Any) -> Dict[str, Dict[str, int]]:
    base = default_team_scoring()["division_points"]
    out: Dict[str, Dict[str, int]] = {}
    raw = raw if isinstance(raw, dict) else {}
    for div in DIVISIONS:
        div_id = div["id"]
        current = raw.get(div_id) if isinstance(raw.get(div_id), dict) else {}
        out[div_id] = {}
        for place in PODIUM_PLACES:
            val = current.get(str(place), base[div_id][str(place)])
            try:
                out[div_id][str(place)] = max(0, int(val))
            except (TypeError, ValueError):
                out[div_id][str(place)] = int(base[div_id][str(place)])
    return out


def _normalize_team_scoring(raw: Any, scores: List[Dict[str, Any]]) -> Dict[str, Any]:
    base = default_team_scoring()
    raw = raw if isinstance(raw, dict) else {}
    score_ids = [str(s.get("id") or "").strip() for s in scores if str(s.get("id") or "").strip()]
    priority_score_id = str(raw.get("priority_score_id") or base["priority_score_id"]).strip()
    if priority_score_id not in score_ids and score_ids:
        priority_score_id = score_ids[-1]

    places_raw = raw.get("places") if isinstance(raw.get("places"), list) else list(base["places"])
    places = []
    for item in places_raw:
        try:
            iv = int(item)
        except (TypeError, ValueError):
            continue
        if iv in PODIUM_PLACES and iv not in places:
            places.append(iv)
    if not places:
        places = list(base["places"])

    return {
        "enabled": bool(raw.get("enabled", True)),
        "priority_score_id": priority_score_id,
        "places": places,
        "division_points": _normalize_division_points(raw.get("division_points")),
    }


def _normalize_participant(raw: Any) -> Dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    try:
        participant_id = int(raw.get("id"))
    except (TypeError, ValueError):
        return None

    sex = str(raw.get("sex") or "").strip().upper()
    if sex not in {"M", "F"}:
        sex = "M"

    category = str(raw.get("category") or "").strip().upper()
    if category not in {"BEGSCAL", "INT"}:
        category = "BEGSCAL"

    division_id = str(raw.get("division_id") or "").strip()
    if division_id not in {d["id"] for d in DIVISIONS}:
        if category == "BEGSCAL" and sex == "M":
            division_id = "BEGSCAL_M"
        elif category == "BEGSCAL" and sex == "F":
            division_id = "BEGSCAL_F"
        elif category == "INT" and sex == "M":
            division_id = "INT_M"
        else:
            division_id = "INT_F"

    try:
        age = int(raw.get("age", 0) or 0)
    except (TypeError, ValueError):
        age = 0

    return {
        "id": participant_id,
        "full_name": str(raw.get("full_name") or "").strip(),
        "sex": sex,
        "birth_date": birth_date_to_storage(raw.get("birth_date")),
        "age": age,
        "category": category,
        "division_id": division_id,
        "region": str(raw.get("region") or "").strip(),
        "city": str(raw.get("city") or "").strip(),
        "club": str(raw.get("club") or raw.get("team_name") or "").strip(),
        "flag_path": raw.get("flag_path") or None,
        "deleted": bool(raw.get("deleted", False)),
    }


def _normalize_db(db: Dict[str, Any]) -> Dict[str, Any]:
    base = default_db()
    if not isinstance(db, dict):
        return base

    settings = db.get("settings") if isinstance(db.get("settings"), dict) else {}
    division_limits = settings.get("division_limits") if isinstance(settings.get("division_limits"), dict) else {}
    scores = settings.get("scores") if isinstance(settings.get("scores"), list) and settings.get("scores") else DEFAULT_SCORES
    display = settings.get("display") if isinstance(settings.get("display"), dict) else {}
    clubs = _normalize_clubs(settings.get("clubs"))
    team_scoring = _normalize_team_scoring(settings.get("team_scoring"), scores)
    try:
        tv_scene_duration_sec = int(settings.get("tv_scene_duration_sec", 10) or 10)
    except (TypeError, ValueError):
        tv_scene_duration_sec = 10
    tv_scene_duration_sec = min(60, max(3, tv_scene_duration_sec))

    participants_raw = db.get("participants") if isinstance(db.get("participants"), list) else []
    participants = []
    for item in participants_raw:
        normalized = _normalize_participant(item)
        if normalized is not None:
            participants.append(normalized)
            club_name = normalized.get("club", "").strip()
            if club_name and club_name.casefold() not in {x.casefold() for x in clubs}:
                clubs.append(club_name)
    clubs = _normalize_clubs(clubs)

    merged_display = default_display_settings()
    for screen_key, screen_defaults in merged_display.items():
        raw_screen = display.get(screen_key) if isinstance(display.get(screen_key), dict) else {}
        merged_display[screen_key] = {**screen_defaults, **raw_screen}

    normalized = {
        "settings": {
            "division_limits": {**base["settings"]["division_limits"], **division_limits},
            "scores": scores,
            "display": merged_display,
            "clubs": clubs,
            "team_scoring": team_scoring,
            "tv_scene_duration_sec": tv_scene_duration_sec,
        },
        "participants": participants,
        "results": db.get("results") if isinstance(db.get("results"), dict) else {},
        "heats": db.get("heats") if isinstance(db.get("heats"), dict) else {},
        "meta": db.get("meta") if isinstance(db.get("meta"), dict) else {},
    }

    normalized["meta"].setdefault("version", 6)
    return normalized


def load_db() -> Dict[str, Any]:
    ensure_dirs()
    if DB_FILE.exists():
        with DB_FILE.open("r", encoding="utf-8") as f:
            db = json.load(f)
        normalized = _normalize_db(db)
        if normalized != db:
            save_db(normalized)
        return normalized

    db = default_db()
    save_db(db)
    return db


def save_db(db: Dict[str, Any]) -> None:
    ensure_dirs()
    normalized = _normalize_db(db)
    tmp_file = DB_FILE.with_suffix(DB_FILE.suffix + ".tmp")
    with tmp_file.open("w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_file, DB_FILE)


def next_participant_id(db: Dict[str, Any]) -> int:
    participants = db.get("participants", [])
    if not participants:
        return 1
    return max(int(p.get("id", 0)) for p in participants) + 1


def get_division_title(division_id: str) -> str:
    for d in DIVISIONS:
        if d["id"] == division_id:
            return d["title"]
    return division_id


def count_participants_in_division(db: Dict[str, Any], division_id: str) -> int:
    return sum(1 for p in db.get("participants", []) if p.get("division_id") == division_id and not p.get("deleted", False))


def delete_participant(db: Dict[str, Any], participant_id: int) -> None:
    for p in db.get("participants", []):
        if int(p["id"]) == int(participant_id):
            p["deleted"] = True
            break


def clear_results(db: Dict[str, Any]) -> None:
    db["results"] = {}


def clear_all_data(db: Dict[str, Any]) -> None:
    db["participants"] = []
    db["results"] = {}
    db["heats"] = {}
