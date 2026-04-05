from __future__ import annotations

from typing import Dict, Any, List, Optional, Tuple

from config import DIVISIONS
from utils import participant_age


def _safe_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _result_of(db: Dict[str, Any], athlete_id: int, score_id: str) -> Optional[Dict[str, Any]]:
    return db.get("results", {}).get(str(athlete_id), {}).get(score_id)


def _active_division_participants(db: Dict[str, Any], division_id: str) -> List[Dict[str, Any]]:
    return [
        p for p in db.get("participants", [])
        if p.get("division_id") == division_id and not p.get("deleted", False)
    ]


def is_score_complete_for_division(db: Dict[str, Any], division_id: str, score_id: str) -> bool:
    participants = _active_division_participants(db, division_id)
    if not participants:
        return False
    return all(_result_of(db, int(p["id"]), score_id) is not None for p in participants)


def completed_score_ids_for_division(db: Dict[str, Any], division_id: str) -> List[str]:
    score_ids = [str(s.get("id") or "") for s in db.get("settings", {}).get("scores", []) if str(s.get("id") or "").strip()]
    return [sid for sid in score_ids if is_score_complete_for_division(db, division_id, sid)]


def has_completed_scores_for_division(db: Dict[str, Any], division_id: str) -> bool:
    return bool(completed_score_ids_for_division(db, division_id))


def is_division_overall_ready(db: Dict[str, Any], division_id: str) -> bool:
    score_ids = [str(s.get("id") or "") for s in db.get("settings", {}).get("scores", []) if str(s.get("id") or "").strip()]
    if not score_ids:
        return False
    return len(completed_score_ids_for_division(db, division_id)) == len(score_ids)


def _sort_key_for_score(score_type: str, result: Optional[Dict[str, Any]]) -> Tuple:
    if result is None:
        return (9,)

    status = result.get("status")
    value = result.get("value")
    num = _safe_float(value)

    if status == "wd":
        return (8,)

    if score_type == "time":
        if status == "ok":
            if num is None:
                return (7,)
            return (0, num)
        if status == "capped":
            if num is None:
                return (7,)
            return (1, -num)
        return (7,)

    if score_type in ("reps", "weight"):
        if status == "ok":
            if num is None:
                return (7,)
            return (0, -num)
        return (7,)

    return (7,)


def _points_for_place(place: int, n: int) -> float:
    if n <= 0:
        return 0.0
    step = 100.0 / float(n)
    pts = 100.0 - (place - 1) * step
    return round(max(0.0, pts), 2)


def build_ranking(db: Dict[str, Any], division_id: str, score_id: str) -> List[Dict[str, Any]]:
    settings = db["settings"]
    sdef = None
    for s in settings.get("scores", []):
        if s["id"] == score_id:
            sdef = s
            break
    if sdef is None:
        return []

    score_type = sdef["type"]
    participants = [
        p for p in db.get("participants", [])
        if p.get("division_id") == division_id and not p.get("deleted", False)
    ]
    n = len(participants)

    rows = []
    for p in participants:
        aid = int(p["id"])
        res = _result_of(db, aid, score_id)
        rows.append({
            "athlete_id": aid,
            "full_name": p.get("full_name", ""),
            "club": p.get("club", ""),
            "city": p.get("city", ""),
            "age": participant_age(p),
            "division_id": division_id,
            "result": res,
        })

    rows_sorted = sorted(
        rows,
        key=lambda r: (_sort_key_for_score(score_type, r["result"]), r["full_name"].lower())
    )

    def cmp_value(r: Dict[str, Any]) -> Tuple:
        res = r["result"]
        if res is None:
            return ("missing",)

        status = res.get("status")
        val = _safe_float(res.get("value"))

        if score_type == "time":
            if status == "ok":
                if val is None:
                    return ("other",)
                return ("ok", val)
            if status == "capped":
                if val is None:
                    return ("other",)
                return ("capped", val)
            if status == "wd":
                return ("wd",)
        else:
            if status == "ok":
                if val is None:
                    return ("other",)
                return ("ok", val)
            if status == "wd":
                return ("wd",)

        return ("other",)

    place = 0
    index = 0
    prev_cmp = None

    for r in rows_sorted:
        index += 1
        cv = cmp_value(r)

        if r["result"] is None:
            r["place"] = None
            r["points"] = None
            continue

        if r["result"].get("status") == "wd":
            r["place"] = None
            r["points"] = 0.0
            continue

        if cv == ("other",):
            r["place"] = None
            r["points"] = None
            continue

        if prev_cmp is None:
            place = 1
        elif cv != prev_cmp:
            place = index

        r["place"] = place
        r["points"] = _points_for_place(place, n)
        prev_cmp = cv

    return rows_sorted


def total_points_for_athlete(db: Dict[str, Any], athlete_id: int) -> Optional[float]:
    div_id = None
    for p in db.get("participants", []):
        if not p.get("deleted", False) and int(p["id"]) == int(athlete_id):
            div_id = p.get("division_id")
            break
    if div_id is None:
        return None

    score_ids = [str(s.get("id") or "") for s in db.get("settings", {}).get("scores", []) if str(s.get("id") or "").strip()]

    total = 0.0
    has_any_points = False
    for sid in score_ids:
        ranking = build_ranking(db, str(div_id), sid)
        for r in ranking:
            if int(r["athlete_id"]) == int(athlete_id):
                pts = r.get("points")
                if pts is not None:
                    total += float(pts)
                    has_any_points = True
                break

    if not has_any_points:
        return None
    return round(total, 2)


def _priority_points_for_athlete(db: Dict[str, Any], athlete_id: int, priority_score_id: str) -> float:
    participant = next((p for p in db.get("participants", []) if not p.get("deleted", False) and int(p["id"]) == int(athlete_id)), None)
    if not participant:
        return -1.0
    ranking = build_ranking(db, str(participant.get("division_id") or ""), priority_score_id)
    for row in ranking:
        if int(row["athlete_id"]) == int(athlete_id):
            pts = row.get("points")
            return -1.0 if pts is None else float(pts)
    return -1.0




def _heat_for_athlete(db: Dict[str, Any], division_id: str, score_id: str, athlete_id: int) -> Optional[int]:
    score_heats = db.get("heats", {}).get(str(score_id), {})
    division_heats = score_heats.get(str(division_id), []) if isinstance(score_heats, dict) else []
    for heat_block in division_heats:
        heat_num = heat_block.get("heat")
        for assignment in heat_block.get("assignments", []):
            if int(assignment.get("athlete_id") or 0) == int(athlete_id):
                try:
                    return int(heat_num)
                except (TypeError, ValueError):
                    return None
    return None


def _place_marker(code: Optional[str]) -> str:
    return {"priority": "*", "heat": "**", "age": "***"}.get(str(code or ""), "")
def build_division_overall(db: Dict[str, Any], division_id: str) -> List[Dict[str, Any]]:
    participants = _active_division_participants(db, division_id)
    team_scoring = db.get("settings", {}).get("team_scoring", {})
    priority_score_id = str(team_scoring.get("priority_score_id") or "").strip()

    rows = []
    for p in participants:
        aid = int(p["id"])
        total = total_points_for_athlete(db, aid)
        priority_points = None
        if priority_score_id:
            raw_priority_points = _priority_points_for_athlete(db, aid, priority_score_id)
            if raw_priority_points >= 0:
                priority_points = round(raw_priority_points, 2)

        heat_value = _heat_for_athlete(db, division_id, priority_score_id, aid) if priority_score_id else None
        age_value = participant_age(p)
        rows.append({
            "id": aid,
            "athlete_id": aid,
            "full_name": p.get("full_name", ""),
            "sex": p.get("sex", ""),
            "age": age_value,
            "category": p.get("category", ""),
            "division_id": division_id,
            "region": p.get("region", "") or p.get("city", ""),
            "city": p.get("city", ""),
            "club": p.get("club", ""),
            "flag_path": p.get("flag_path"),
            "total": total,
            "priority_points": priority_points,
            "priority_heat": heat_value,
            "place": None,
            "place_label": None,
            "display_place": None,
            "display_place_label": None,
            "tie_break_code": None,
            "tie_break_marker": "",
        })

    def sort_key(r: Dict[str, Any]) -> Tuple:
        return (
            0 if r["total"] is not None else 1,
            -float(r["total"] or 0.0),
            -float(r["priority_points"] if r["priority_points"] is not None else -1.0),
            int(r["priority_heat"] if r["priority_heat"] is not None else 9999),
            -int(r["age"] or 0),
            r["full_name"].lower(),
        )

    rows.sort(key=sort_key)

    total_groups: Dict[float, List[Dict[str, Any]]] = {}
    for row in rows:
        if row["total"] is None:
            continue
        total_groups.setdefault(float(row["total"]), []).append(row)

    for group in total_groups.values():
        if len(group) <= 1:
            continue
        priority_keys = {float(r["priority_points"] if r["priority_points"] is not None else -1.0) for r in group}
        if len(priority_keys) > 1:
            for r in group:
                r["tie_break_code"] = "priority"
            continue
        heat_keys = {int(r["priority_heat"] if r["priority_heat"] is not None else 9999) for r in group}
        if len(heat_keys) > 1:
            for r in group:
                r["tie_break_code"] = "heat"
            continue
        age_keys = {int(r["age"] or 0) for r in group}
        if len(age_keys) > 1:
            for r in group:
                r["tie_break_code"] = "age"

    place = 0
    placed_index = 0
    prev_key = None
    for row in rows:
        if row["total"] is None:
            row["place"] = None
            row["place_label"] = None
            continue
        placed_index += 1
        tie_key = (
            float(row["total"] or 0.0),
            float(row["priority_points"] if row["priority_points"] is not None else -1.0),
            int(row["priority_heat"] if row["priority_heat"] is not None else 9999),
            int(row["age"] or 0),
        )
        if prev_key is None or tie_key != prev_key:
            place = placed_index
        row["place"] = place
        marker = _place_marker(row.get("tie_break_code"))
        row["tie_break_marker"] = marker
        row["place_label"] = str(place)
        row["display_place"] = place
        row["display_place_label"] = str(place)
        row["total_label"] = f"{row['total']}{marker}" if row.get("total") is not None and marker else row.get("total")
        prev_key = tie_key

    next_display_place = placed_index
    for row in rows:
        if row["place"] is not None:
            continue
        next_display_place += 1
        row["display_place"] = next_display_place
        row["display_place_label"] = str(next_display_place)
        row["total_label"] = row.get("total")
    return rows


def build_club_ranking(db: Dict[str, Any]) -> Dict[str, Any]:
    settings = db.get("settings", {})
    team_scoring = settings.get("team_scoring", {}) if isinstance(settings.get("team_scoring"), dict) else {}
    division_points = team_scoring.get("division_points", {}) if isinstance(team_scoring.get("division_points"), dict) else {}
    enabled_places = {int(x) for x in team_scoring.get("places", [1, 2, 3]) if str(x).isdigit()}
    priority_score_id = str(team_scoring.get("priority_score_id") or "").strip()

    participants = [p for p in db.get("participants", []) if not p.get("deleted", False)]
    all_club_names = []
    seen = set()
    for name in settings.get("clubs", []):
        club_name = str(name or "").strip()
        if club_name and club_name.casefold() not in seen:
            all_club_names.append(club_name)
            seen.add(club_name.casefold())
    for p in participants:
        club_name = str(p.get("club") or "").strip()
        if club_name and club_name.casefold() not in seen:
            all_club_names.append(club_name)
            seen.add(club_name.casefold())

    club_settings = settings.get("club_settings", {}) if isinstance(settings.get("club_settings"), dict) else {}

    club_rows: Dict[str, Dict[str, Any]] = {
        name: {
            "club_name": name,
            "club_city": str((club_settings.get(name) or {}).get("city") or "").strip(),
            "club_flag": (club_settings.get(name) or {}).get("flag_path"),
            "points": 0.0,
            "participants_count": 0,
            "contributors": 0,
            "first_places": 0,
            "second_places": 0,
            "third_places": 0,
            "priority_sum": 0.0,
            "breakdown": [],
        }
        for name in all_club_names
    }

    for p in participants:
        club_name = str(p.get("club") or "").strip()
        if club_name:
            club_rows.setdefault(club_name, {
                "club_name": club_name,
                "club_city": str((club_settings.get(club_name) or {}).get("city") or "").strip(),
                "club_flag": (club_settings.get(club_name) or {}).get("flag_path"),
                "points": 0.0,
                "participants_count": 0,
                "contributors": 0,
                "first_places": 0,
                "second_places": 0,
                "third_places": 0,
                "priority_sum": 0.0,
                "breakdown": [],
            })
            club_rows[club_name]["participants_count"] += 1

    for division_id, points_map in division_points.items():
        if not has_completed_scores_for_division(db, division_id):
            continue
        overall_rows = build_division_overall(db, division_id)
        for row in overall_rows:
            place = row.get("place")
            club_name = str(row.get("club") or "").strip()
            if not club_name or place not in enabled_places:
                continue
            pts = float(points_map.get(str(place), 0) or 0)
            if pts <= 0:
                continue
            club_row = club_rows.setdefault(club_name, {
                "club_name": club_name,
                "club_city": str((club_settings.get(club_name) or {}).get("city") or "").strip(),
                "club_flag": (club_settings.get(club_name) or {}).get("flag_path"),
                "points": 0.0,
                "participants_count": 0,
                "contributors": 0,
                "first_places": 0,
                "second_places": 0,
                "third_places": 0,
                "priority_sum": 0.0,
                "breakdown": [],
            })
            club_row["points"] += pts
            club_row["contributors"] += 1
            if place == 1:
                club_row["first_places"] += 1
            elif place == 2:
                club_row["second_places"] += 1
            elif place == 3:
                club_row["third_places"] += 1
            priority_pts = _priority_points_for_athlete(db, int(row["athlete_id"]), priority_score_id) if priority_score_id else -1.0
            if priority_pts > 0:
                club_row["priority_sum"] += priority_pts
            club_row["breakdown"].append({
                "athlete_id": int(row["athlete_id"]),
                "full_name": row.get("full_name", ""),
                "division_id": division_id,
                "division_title": division_id,
                "place": place,
                "place_label": str(place) if place else "—",
                "awarded_points": round(pts, 2),
                "priority_points": round(priority_pts, 2) if priority_pts >= 0 else None,
            })

    division_title_map = {d["id"]: d["title"] for d in DIVISIONS}
    rows = list(club_rows.values())
    for row in rows:
        row["points"] = round(float(row["points"]), 2)
        row["priority_sum"] = round(float(row["priority_sum"]), 2)
        for item in row["breakdown"]:
            item["division_title"] = division_title_map.get(item["division_id"], item["division_id"])
        row["breakdown"].sort(key=lambda x: (-float(x.get("awarded_points") or 0), x.get("full_name", "").lower()))

    rows.sort(
        key=lambda x: (
            -float(x["points"]),
            -int(x["first_places"]),
            -int(x["second_places"]),
            -int(x["third_places"]),
            -float(x["priority_sum"]),
            int(x["participants_count"]),
            x["club_name"].lower(),
        )
    )
    for idx, row in enumerate(rows, start=1):
        row["place"] = idx
    return {
        "rows": rows,
        "priority_score_id": priority_score_id,
        "places": sorted(enabled_places),
    }