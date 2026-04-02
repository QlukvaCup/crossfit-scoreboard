import pandas as pd
import streamlit as st
from storage import load_db
from config import DIVISIONS
from scoring import build_ranking, build_division_overall, build_club_ranking
from utils import compact_page_style, display_result_value, participant_age

st.set_page_config(page_title="Tables", layout="wide")
compact_page_style()
st.title("📊 Tables (админ-панель)")

db = load_db()
settings = db["settings"]
scores = settings["scores"]
team_scoring = settings.get("team_scoring", {})


def display_value_for_public(sdef, res):
    if res is None:
        return "—"
    status = res.get("status")
    val = res.get("value")
    if status == "wd":
        return "Снялся"
    if status == "capped":
        pretty = display_result_value({"type": "reps"}, val)
        return f"CAP {pretty}" if pretty else "CAP"
    return display_result_value(sdef, val)


for div in DIVISIONS:
    div_id = div["id"]
    st.subheader(div["title"])

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

    has_live_places = any(r.get("place") is not None for r in overall_rows)

    table_rows = []
    for p in participants:
        aid = int(p["id"])
        overall = overall_map.get(aid, {})
        total_value = overall.get("total")
        priority_value = overall.get("priority_points")
        row = {
            "Место": overall.get("display_place_label") or overall.get("place_label") or "—",
            "ФИО": p.get("full_name", ""),
            "Возраст": participant_age(p),
            "DIV": p.get("category", ""),
            "Регион": p.get("region", "") or p.get("city", ""),
            "Клуб": p.get("club", "") or "—",
            "Флаг": "✅" if p.get("flag_path") else "—",
        }
        for s in scores:
            sid = s["id"]
            pts = points_maps[sid].get(aid)
            res = result_maps[sid].get(aid)
            row[f"{sid}"] = "—" if pts is None else pts
            row[f"{sid}_res"] = display_value_for_public(s, res)
        row["Приоритет"] = priority_value if priority_value is not None else "—"
        row["ИТОГО"] = total_value if total_value is not None else "—"
        table_rows.append(row)

    if has_live_places:
        table_rows.sort(
            key=lambda r: (
                0 if isinstance(r["ИТОГО"], (int, float)) else 1,
                -float(r["ИТОГО"] if isinstance(r["ИТОГО"], (int, float)) else 0.0),
                -float(r["Приоритет"]) if isinstance(r["Приоритет"], (int, float)) else 1,
                r["ФИО"].lower(),
            )
        )
    else:
        table_rows.sort(key=lambda r: r["ФИО"].lower())

    df = pd.DataFrame(table_rows)
    styled = df.style.set_properties(subset=["Клуб"], **{"font-weight": "700"})
    st.dataframe(styled, use_container_width=True, hide_index=True)
    st.divider()

st.subheader("Клубный зачёт")
club_payload = build_club_ranking(db)
club_rows = []
for row in club_payload.get("rows", []):
    club_rows.append({
        "Место": row.get("place"),
        "Клуб": row.get("team_name"),
        "Очки": row.get("points"),
        "Участников": row.get("participants_count"),
        "Зачётных мест": row.get("contributors"),
        "1 мест": row.get("first_places"),
        "2 мест": row.get("second_places"),
        "3 мест": row.get("third_places"),
        "Приоритетный комплекс": row.get("priority_sum"),
    })
if club_rows:
    st.dataframe(club_rows, use_container_width=True, hide_index=True)
else:
    st.info("Клубный зачёт появится после полного ввода хотя бы одного комплекса в зачётном дивизионе.")

st.caption(
    f"Командный зачёт обновляется после полного закрытия комплекса в дивизионе. Приоритетный комплекс для тай-брейка: {team_scoring.get('priority_score_id', '—')}."
)
