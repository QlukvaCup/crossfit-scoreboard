import base64
import json
import mimetypes
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

from config import DOCS_DIR, DOCS_RESULTS_FILE, DOCS_FLAGS_DIR, DIVISIONS
from heats_logic import serialize_heats_for_public
from storage import load_db, default_display_settings
from scoring import build_ranking, total_points_for_athlete
from utils import display_result_value


def ensure_docs_dirs() -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_FLAGS_DIR.mkdir(parents=True, exist_ok=True)


def _flag_data_uri(flag_path: Optional[str]) -> Optional[str]:
    if not flag_path:
        return None
    src = Path(flag_path)
    if not src.is_absolute():
        src = Path.cwd() / src
    if not src.exists() or not src.is_file():
        return None
    mime_type, _ = mimetypes.guess_type(src.name)
    mime_type = mime_type or "image/png"
    try:
        encoded = base64.b64encode(src.read_bytes()).decode("ascii")
    except OSError:
        return None
    return f"data:{mime_type};base64,{encoded}"


def _public_result_text(score_def: Dict[str, Any], result: Optional[Dict[str, Any]]) -> str:
    if not result:
        return ""
    status = result.get("status")
    value = result.get("value")
    if status == "wd":
        return "WD"
    if status == "capped":
        pretty = display_result_value(score_def, value)
        return f"CAP {pretty}" if pretty else "CAP"
    return display_result_value(score_def, value)


def _assign_places_by_total(rows: List[Dict[str, Any]]) -> None:
    place = 0
    prev_total = None
    for index, row in enumerate(rows, start=1):
        total = float(row.get("total") or 0.0)
        if prev_total is None or total != prev_total:
            place = index
        row["place"] = place
        row["place_label"] = str(place)
        prev_total = total


def _build_clubs(rows_by_division: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    clubs: Dict[str, Dict[str, Any]] = {}
    for div_id, div in rows_by_division.items():
        div_title = div.get("title", div_id)
        for row in div.get("rows", []):
            club_name = (row.get("club") or "").strip()
            if not club_name:
                continue
            entry = clubs.setdefault(
                club_name,
                {
                    "club_name": club_name,
                    "points": 0.0,
                    "participants_count": 0,
                    "contributors": 0,
                    "first_places": 0,
                    "breakdown": [],
                    "members": set(),
                },
            )
            athlete_id = int(row.get("id") or 0)
            if athlete_id and athlete_id not in entry["members"]:
                entry["members"].add(athlete_id)
                entry["participants_count"] += 1

            awarded = float(row.get("total") or 0.0)
            entry["points"] += awarded
            if awarded > 0:
                entry["contributors"] += 1
            if int(row.get("place") or 0) == 1:
                entry["first_places"] += 1

            entry["breakdown"].append(
                {
                    "full_name": row.get("full_name", ""),
                    "division_title": div_title,
                    "place": row.get("place"),
                    "place_label": row.get("place_label") or row.get("place"),
                    "awarded_points": round(awarded, 2),
                }
            )

    club_rows = []
    for club in clubs.values():
        club["points"] = round(club["points"], 2)
        club["breakdown"].sort(key=lambda item: (-float(item.get("awarded_points") or 0.0), item.get("full_name") or ""))
        club.pop("members", None)
        club_rows.append(club)

    club_rows.sort(key=lambda r: (-float(r["points"]), -int(r["contributors"]), -int(r["first_places"]), r["club_name"].lower()))
    place = 0
    prev_points = None
    for idx, row in enumerate(club_rows, start=1):
        pts = float(row["points"])
        if prev_points is None or pts != prev_points:
            place = idx
        row["place"] = place
        prev_points = pts

    return {"title": "Клубный зачёт", "rows": club_rows}


def build_public_payload() -> Dict[str, Any]:
    db = load_db()
    settings = db["settings"]
    scores = settings["scores"]
    display = settings.get("display") or default_display_settings()

    payload: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "divisions": {},
        "scores": scores,
        "heats": serialize_heats_for_public(db),
        "display": display,
        "clubs": {"title": "Клубный зачёт", "rows": []},
    }

    for d in DIVISIONS:
        div_id = d["id"]
        participants = [
            p for p in db.get("participants", [])
            if p.get("division_id") == div_id and not p.get("deleted", False)
        ]

        points_maps = {}
        result_maps = {}
        for s in scores:
            ranking = build_ranking(db, div_id, s["id"])
            points_maps[s["id"]] = {r["athlete_id"]: r.get("points") for r in ranking}
            result_maps[s["id"]] = {r["athlete_id"]: r.get("result") for r in ranking}

        rows = []
        sorted_participants = sorted(participants, key=lambda p: (-total_points_for_athlete(db, int(p["id"])), p.get("full_name", "")))
        for p in sorted_participants:
            aid = int(p["id"])
            row = {
                "place": None,
                "place_label": None,
                "id": aid,
                "full_name": p.get("full_name", ""),
                "age": p.get("age", ""),
                "club": p.get("club", ""),
                "region": p.get("region", "") or p.get("city", ""),
                "city": p.get("city", ""),
                "category": p.get("category", ""),
                "division_id": div_id,
                "flag": _flag_data_uri(p.get("flag_path")),
                "scores": {},
                "total": round(total_points_for_athlete(db, aid), 2),
            }
            for s in scores:
                sid = s["id"]
                raw_result = result_maps[sid].get(aid)
                row["scores"][sid] = {
                    "points": points_maps[sid].get(aid),
                    "result": raw_result,
                    "result_text": _public_result_text(s, raw_result),
                }
            rows.append(row)

        _assign_places_by_total(rows)
        payload["divisions"][div_id] = {"title": d["title"], "rows": rows}

    payload["clubs"] = _build_clubs(payload["divisions"])
    return payload


def copy_flags_to_docs() -> None:
    ensure_docs_dirs()
    if DOCS_FLAGS_DIR.exists():
        for f in DOCS_FLAGS_DIR.glob("*"):
            if f.is_file():
                f.unlink()
    db = load_db()
    for p in db.get("participants", []):
        if p.get("deleted", False) or not p.get("flag_path"):
            continue
        src = Path(p["flag_path"])
        if not src.exists():
            continue
        shutil.copyfile(src, DOCS_FLAGS_DIR / f"athlete_{p['id']}.png")


def write_public_results(payload: Dict[str, Any]) -> None:
    ensure_docs_dirs()
    with DOCS_RESULTS_FILE.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def build_all() -> None:
    payload = build_public_payload()
    copy_flags_to_docs()
    write_public_results(payload)


if __name__ == "__main__":
    build_all()
    print(f"OK: wrote {DOCS_RESULTS_FILE}")
