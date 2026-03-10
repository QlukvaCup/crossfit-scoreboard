import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

from config import DOCS_DIR, DOCS_RESULTS_FILE, DOCS_FLAGS_DIR, DIVISIONS
from heats_logic import serialize_heats_for_public
from storage import load_db
from scoring import build_ranking, total_points_for_athlete
from utils import display_result_value


def ensure_docs_dirs() -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_FLAGS_DIR.mkdir(parents=True, exist_ok=True)


def build_public_payload() -> Dict[str, Any]:
    db = load_db()
    settings = db["settings"]
    scores = settings["scores"]

    payload: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "divisions": {},
        "scores": scores,
        "heats": serialize_heats_for_public(db),
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
        sorted_participants = sorted(
            participants,
            key=lambda p: (-total_points_for_athlete(db, int(p["id"])), p.get("full_name", ""))
        )

        for idx, p in enumerate(sorted_participants, start=1):
            aid = int(p["id"])
            row = {
                "place": idx,
                "id": aid,
                "full_name": p.get("full_name", ""),
                "age": p.get("age", ""),
                "club": p.get("club", ""),
                "city": p.get("city", ""),
                "category": p.get("category", ""),
                "division_id": div_id,
                "flag": f"flags/athlete_{aid}.png" if p.get("flag_path") else None,
                "scores": {},
                "total": total_points_for_athlete(db, aid),
            }
            for s in scores:
                sid = s["id"]
                row["scores"][sid] = {
                    "points": points_maps[sid].get(aid),
                    "result": result_maps[sid].get(aid),
                    "result_text": display_result_value(s, result_maps[sid].get(aid)),
                }
            rows.append(row)

        payload["divisions"][div_id] = {
            "title": d["title"],
            "rows": rows,
        }

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