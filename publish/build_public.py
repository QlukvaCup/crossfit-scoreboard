import json
import mimetypes
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

from config import DOCS_DIR, DOCS_RESULTS_FILE, DOCS_FLAGS_DIR, DIVISIONS
from heats_logic import serialize_heats_for_public
from storage import load_db, default_display_settings
from scoring import build_ranking, build_division_overall, build_club_ranking
from utils import display_result_value, participant_age


try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


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
        return "Снялся"
    if status == "capped":
        pretty = display_result_value({"type": "reps"}, value)
        return f"CAP {pretty}" if pretty else "CAP"
    return display_result_value(score_def, value)


def _division_title_map() -> Dict[str, str]:
    return {d["id"]: d["title"] for d in DIVISIONS}


def build_public_payload() -> Dict[str, Any]:
    db = load_db()
    settings = db["settings"]
    scores = settings["scores"]
    team_scoring = settings.get("team_scoring", {})
    display = settings.get("display") if isinstance(settings.get("display"), dict) else default_display_settings()

    payload: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tv_scene_duration_sec": int(settings.get("tv_scene_duration_sec", 10) or 10),
        "divisions": {},
        "scores": scores,
        "heats": serialize_heats_for_public(db),
        "display": display,
        "tie_break_mode": "priority_score",
        "priority_score_id": team_scoring.get("priority_score_id"),
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

        overall_rows = build_division_overall(db, div_id)
        overall_map = {int(r["athlete_id"]): r for r in overall_rows}

        rows: List[Dict[str, Any]] = []
        for p in participants:
            aid = int(p["id"])
            overall = overall_map.get(aid, {})
            row = {
                "place": overall.get("display_place", overall.get("place")),
                "place_label": overall.get("display_place_label") or overall.get("place_label"),
                "sport_place": overall.get("place"),
                "sport_place_label": overall.get("place_label"),
                "id": aid,
                "full_name": p.get("full_name", ""),
                "age": participant_age(p),
                "club": p.get("club", ""),
                "region": p.get("region", "") or p.get("city", ""),
                "city": p.get("city", ""),
                "category": p.get("category", ""),
                "division_id": div_id,
                "flag": _flag_data_uri(p.get("flag_path")),
                "scores": {},
                "priority_points": overall.get("priority_points"),
                "total": overall.get("total"),
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

        rows.sort(
            key=lambda r: (
                int(r.get("place") or 9999),
                r.get("full_name", "").lower(),
            ) if r.get("place") is not None else (
                9999,
                r.get("full_name", "").lower(),
            )
        )

        payload["divisions"][div_id] = {
            "title": d["title"],
            "rows": rows,
        }

    club_payload = build_club_ranking(db)
    div_titles = _division_title_map()
    for row in club_payload.get("rows", []):
        row["club_flag"] = _flag_data_uri(row.get("club_flag"))
        for item in row.get("breakdown", []):
            item["division_title"] = div_titles.get(item.get("division_id"), item.get("division_id"))
    payload["clubs"] = club_payload
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
        if src.exists():
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
