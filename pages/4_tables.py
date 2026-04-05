import html

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


def esc(value):
    if value is None:
        return ""
    return html.escape(str(value))


st.markdown(
    """
    <style>
    .admin-results-table-wrap{overflow-x:auto;margin-bottom:8px;}
    .admin-results-table{
        width:100%;
        border-collapse:collapse;
        font-size:14px;
        background:transparent;
    }
    .admin-results-table th,
    .admin-results-table td{
        border-bottom:1px solid rgba(255,255,255,0.10);
        padding:6px 8px;
        text-align:left;
        vertical-align:top;
        white-space:nowrap;
        background:transparent !important;
        color:#f3f4f6;
    }
    .admin-results-table th{
        background:rgba(255,255,255,0.04) !important;
        font-weight:700;
        color:#ffffff;
    }
    .admin-results-table tbody tr,
    .admin-results-table tbody tr:hover{
        background:transparent !important;
    }
    .admin-results-table td.club-cell,
    .admin-results-table td.total-cell{
        font-weight:700;
        color:#ffffff;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def render_html_table(headers, body_rows):
    head_html = "<tr>" + "".join(f"<th>{esc(h)}</th>" for h in headers) + "</tr>"
    table_html = (
        '<div class="admin-results-table-wrap"><table class="admin-results-table"><thead>'
        + head_html
        + "</thead><tbody>"
        + "".join(body_rows)
        + "</tbody></table></div>"
    )
    st.markdown(table_html, unsafe_allow_html=True)


def render_admin_table(rows, score_ids):
    if not rows:
        st.info("Нет данных")
        return

    headers = ["#", "Участник", "Возраст", "Категория", "Город / регион", "Клуб", "Флаг"]
    for sid in score_ids:
        headers.append(f"{sid} очки")
        headers.append(f"{sid} результат")
    headers.extend(["Приоритет", "Итого"])

    body_rows = []
    for row in rows:
        parts = [
            "<tr>",
            f"<td>{esc(row.get('Место', '—'))}</td>",
            f"<td>{esc(row.get('ФИО', ''))}</td>",
            f"<td>{esc(row.get('Возраст', ''))}</td>",
            f"<td>{esc(row.get('DIV', ''))}</td>",
            f"<td>{esc(row.get('Регион', ''))}</td>",
            f"<td class='club-cell'>{esc(row.get('Клуб', ''))}</td>",
            f"<td>{esc(row.get('Флаг', '—'))}</td>",
        ]
        for sid in score_ids:
            parts.append(f"<td>{esc(row.get(sid, '—'))}</td>")
            parts.append(f"<td>{esc(row.get(f'{sid}_res', '—'))}</td>")
        parts.append(f"<td>{esc(row.get('Приоритет', '—'))}</td>")
        parts.append(f"<td class='total-cell'>{esc(row.get('ИТОГО', '—'))}</td>")
        parts.append("</tr>")
        body_rows.append("".join(parts))

    render_html_table(headers, body_rows)


def render_tie_break_notes(rows):
    codes = {str(r.get("TB_CODE") or "") for r in rows if r.get("TB_CODE")}
    notes = []
    if "priority" in codes:
        notes.append("* место определено по приоритетному комплексу")
    if "heat" in codes:
        notes.append("** место определено по заходу")
    if "age" in codes:
        notes.append("*** место определено по возрасту")
    if notes:
        st.markdown("<div style='margin:8px 0 18px 0; font-size:13px; color:#cbd5e1;'>" + "<br>".join(notes) + "</div>", unsafe_allow_html=True)


for div in DIVISIONS:
    div_id = div["id"]
    st.subheader(div["title"])
    participants = [p for p in db.get("participants", []) if p.get("division_id") == div_id and not p.get("deleted", False)]

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
            "TB_CODE": overall.get("tie_break_code"),
            "ФИО": p.get("full_name", ""),
            "Возраст": participant_age(p),
            "DIV": p.get("category", ""),
            "Регион": p.get("region", "") or p.get("city", ""),
            "Клуб": p.get("club", ""),
            "Флаг": "✅" if p.get("flag_path") else "—",
        }
        for s in scores:
            sid = s["id"]
            pts = points_maps[sid].get(aid)
            res = result_maps[sid].get(aid)
            row[f"{sid}"] = "—" if pts is None else pts
            row[f"{sid}_res"] = display_value_for_public(s, res)
        row["Приоритет"] = priority_value if priority_value is not None else "—"
        marker = overall.get("tie_break_marker") or ""
        row["ИТОГО"] = (f"{total_value}{marker}" if total_value is not None and marker else (total_value if total_value is not None else "—"))
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

    render_admin_table(table_rows, [s["id"] for s in scores])
    render_tie_break_notes(table_rows)
    st.divider()

st.subheader("Клубный зачёт")
club_payload = build_club_ranking(db)
club_rows = []
for row in club_payload.get("rows", []):
    club_rows.append({
        "Место": row.get("place"),
        "Клуб": row.get("club_name"),
        "Город": row.get("club_city", ""),
        "Флаг": "✅" if row.get("club_flag") else "—",
        "Очки": row.get("points"),
        "Участников": row.get("participants_count"),
        "Зачётных мест": row.get("contributors"),
        "1 мест": row.get("first_places"),
        "2 мест": row.get("second_places"),
        "3 мест": row.get("third_places"),
        "Приоритет": row.get("priority_sum"),
    })
if club_rows:
    club_headers = ["#", "Клуб", "Город", "Флаг", "Очки", "Участников", "Зачётных мест", "1 мест", "2 мест", "3 мест", "Приоритет"]
    club_body = []
    for row in club_rows:
        club_body.append(
            "<tr>"
            f"<td>{esc(row.get('Место', '—'))}</td>"
            f"<td class='club-cell'>{esc(row.get('Клуб', ''))}</td>"
            f"<td>{esc(row.get('Город', ''))}</td>"
            f"<td>{esc(row.get('Флаг', '—'))}</td>"
            f"<td class='total-cell'>{esc(row.get('Очки', '—'))}</td>"
            f"<td>{esc(row.get('Участников', '—'))}</td>"
            f"<td>{esc(row.get('Зачётных мест', '—'))}</td>"
            f"<td>{esc(row.get('1 мест', '—'))}</td>"
            f"<td>{esc(row.get('2 мест', '—'))}</td>"
            f"<td>{esc(row.get('3 мест', '—'))}</td>"
            f"<td>{esc(row.get('Приоритет', '—'))}</td>"
            "</tr>"
        )
    render_html_table(club_headers, club_body)
else:
    st.info("Клубный зачёт появится после полного ввода хотя бы одного комплекса в зачётном дивизионе.")

scored_clubs = [row for row in club_payload.get("rows", []) if float(row.get("points") or 0) > 0]
if scored_clubs:
    st.markdown("### Детализация по клубам")
    for row in scored_clubs:
        city = str(row.get("club_city") or "").strip()
        title = row.get("club_name") or "Клуб"
        if city:
            title += f" — {city}"
        st.markdown(f"**{title}**")
        for item in row.get("breakdown", []):
            st.write(f"- {item.get('full_name', '')} · {item.get('division_title', '')} · место {item.get('place_label', '—')} · {item.get('awarded_points', 0)} очк.")
        st.divider()

st.caption(f"Клубный зачёт обновляется после полного закрытия комплекса в дивизионе. Приоритетный комплекс для тай-брейка: {team_scoring.get('priority_score_id', '—')}.")
