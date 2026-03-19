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
        import base64
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


def _division_title_map() -> Dict[str, str]:
    return {d["id"]: d["title"] for d in DIVISIONS}


def _build_clubs_payload(db: Dict[str, Any], division_rows: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    division_titles = _division_title_map()
    participants = [
        p for p in db.get("participants", [])
        if not p.get("deleted", False) and str(p.get("club") or "").strip()
    ]

    clubs: Dict[str, Dict[str, Any]] = {}
    for p in participants:
        club_name = str(p.get("club") or "").strip()
        aid = int(p["id"])
        clubs.setdefault(
            club_name,
            {
                "club_name": club_name,
                "team_name": club_name,
                "club": club_name,
                "points": 0.0,
                "participants_count": 0,
                "contributors": 0,
                "first_places": 0,
                "breakdown": [],
            },
        )
        club_row = clubs[club_name]
        club_row["participants_count"] += 1
        total = float(total_points_for_athlete(db, aid))
        if total > 0:
            club_row["contributors"] += 1
            club_row["points"] += total

        division_id = p.get("division_id")
        division_list = division_rows.get(division_id, [])
        person_place = None
        for row in division_list:
            if int(row["id"]) == aid:
                person_place = row.get("place")
                break
        if person_place == 1:
            club_row["first_places"] += 1

        club_row["breakdown"].append(
            {
                "athlete_id": aid,
                "full_name": p.get("full_name", ""),
                "division_id": division_id,
                "division_title": division_titles.get(division_id, division_id),
                "place": person_place,
                "place_label": str(person_place) if person_place else "—",
                "awarded_points": round(total, 2),
            }
        )

    rows = list(clubs.values())
    for row in rows:
        row["points"] = round(float(row["points"]), 2)
        row["breakdown"].sort(
            key=lambda x: (-float(x.get("awarded_points") or 0.0), x.get("full_name", "").lower())
        )

    rows.sort(
        key=lambda x: (-float(x["points"]), x["participants_count"], -int(x["first_places"]), x["club_name"].lower())
    )
    for idx, row in enumerate(rows, start=1):
        row["place"] = idx

    return {"rows": rows}


def build_public_payload() -> Dict[str, Any]:
    db = load_db()
    settings = db["settings"]
    scores = settings["scores"]
    display = settings.get("display") if isinstance(settings.get("display"), dict) else default_display_settings()

    payload: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "divisions": {},
        "scores": scores,
        "heats": serialize_heats_for_public(db),
        "display": display,
    }

    division_rows: Dict[str, List[Dict[str, Any]]] = {}

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
        sorted_participants = sorted(
            participants,
            key=lambda p: (-total_points_for_athlete(db, int(p["id"])), p.get("full_name", "")),
        )

        for p in sorted_participants:
            aid = int(p["id"])
            row = {
                "place": None,
                "place_label": None,
                "id": aid,
                "full_name": p.get("full_name", ""),
                "age": p.get("age", ""),
                "club": p.get("club", ""),
                "team_name": p.get("club", ""),
                "region": p.get("region", "") or p.get("city", ""),
                "city": p.get("city", ""),
                "category": p.get("category", ""),
                "division_id": div_id,
                "flag": _flag_data_uri(p.get("flag_path")),
                "scores": {},
                "total": total_points_for_athlete(db, aid),
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
        division_rows[div_id] = rows

        payload["divisions"][div_id] = {
            "title": d["title"],
            "rows": rows,
        }

    payload["clubs"] = _build_clubs_payload(db, division_rows)
    payload["teams"] = payload["clubs"]
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
