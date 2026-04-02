import pandas as pd
import streamlit as st

from storage import load_db, save_db
from config import DIVISIONS
from utils import compact_page_style, parse_time_mmss, format_time_mmss, display_result_value

st.set_page_config(page_title="Results Entry", layout="wide")
compact_page_style()
st.title("🧾 Results Entry")

db = load_db()
settings = db["settings"]
scores = settings["scores"]

div_titles = {d["title"]: d["id"] for d in DIVISIONS}
score_titles = {f"{s['id']} — {s['title']}": s["id"] for s in scores}
STATUS_LABELS = {"ok": "Зачтено", "capped": "CAP", "wd": "Снялся"}
LABEL_TO_STATUS = {v: k for k, v in STATUS_LABELS.items()}


def display_result_for_entry(score_def, res):
    if res is None:
        return ""
    status = res.get("status")
    value = res.get("value")
    if status == "wd":
        return "Снялся"
    if status == "capped":
        reps_text = display_result_value({"type": "reps"}, value)
        return f"CAP {reps_text}" if reps_text else "CAP"
    return display_result_value(score_def, value)


colA, colB = st.columns(2)
with colA:
    div_label = st.selectbox("Дивизион", list(div_titles.keys()))
    division_id = div_titles[div_label]
with colB:
    score_label = st.selectbox("Зачёт / Комплекс", list(score_titles.keys()))
    score_id = score_titles[score_label]

sdef = next(s for s in scores if s["id"] == score_id)
stype = sdef["type"]
cap_enabled = bool(sdef.get("time_cap_enabled", False))

st.info(f"Тип зачёта: **{stype}**. Time cap: **{cap_enabled}**")

participants = [
    p for p in db.get("participants", [])
    if p.get("division_id") == division_id and not p.get("deleted", False)
]
participants.sort(key=lambda p: (p.get("full_name") or "").lower())

if not participants:
    st.warning("В этом дивизионе нет участников.")
    st.stop()

options = []
id_by_label = {}
for p in participants:
    region = p.get("region", "") or p.get("city", "")
    label = f"{p['full_name']} ({p.get('club', '')}, {region}) [ID:{p['id']}]"
    options.append(label)
    id_by_label[label] = int(p["id"])

st.subheader("Ввод результата через форму")
ath_label = st.selectbox("Атлет", options)
ath_id = id_by_label[ath_label]
existing = db.get("results", {}).get(str(ath_id), {}).get(score_id) or {}


def _time_key():
    return f"time_input_{division_id}_{score_id}_{ath_id}"


def _time_context_key():
    return f"time_input_context_{division_id}_{score_id}"


time_key = _time_key()
time_context_key = _time_context_key()
current_context = f"{division_id}|{score_id}|{ath_id}"

if stype == "time":
    previous_context = st.session_state.get(time_context_key)
    if previous_context != current_context or time_key not in st.session_state:
        st.session_state[time_key] = (
            format_time_mmss(existing.get("value"))
            if existing.get("status") == "ok"
            else ""
        )
        st.session_state[time_context_key] = current_context

col1, col2 = st.columns(2)
with col1:
    withdrawn = st.checkbox("Снялся", value=existing.get("status") == "wd")
with col2:
    capped = st.checkbox(
        "CAP",
        value=existing.get("status") == "capped",
        disabled=not (stype == "time" and cap_enabled),
    )

disabled_input = withdrawn
value = None
raw_time_value = ""

if stype == "time":
    if capped and cap_enabled:
        value = st.number_input(
            "Повторы при CAP",
            min_value=0,
            step=1,
            value=int(existing.get("value") or 0) if existing.get("status") == "capped" else 0,
            disabled=disabled_input,
        )
        st.caption("Для CAP время рядом не показывается — только CAP и повторения.")
    else:
        raw_time_value = st.text_input(
            "Время (mm:ss)",
            key=time_key,
            placeholder="Например: 534 или 5:34",
            disabled=disabled_input,
        )
        parsed_preview = parse_time_mmss(raw_time_value)
        if raw_time_value:
            if parsed_preview is not None:
                st.caption(f"Будет сохранено как: {format_time_mmss(parsed_preview)}")
            else:
                st.caption("Введи время как mm:ss или просто цифрами, например 534 → 5:34")
        else:
            st.caption("Можно вводить без двоеточия: 534 → 5:34, 6214 → 62:14")
elif stype == "reps":
    value = st.number_input(
        "Повторы",
        min_value=0,
        step=1,
        value=int(existing.get("value") or 0) if existing.get("status") == "ok" else 0,
        disabled=disabled_input,
    )
elif stype == "weight":
    value = st.number_input(
        "Вес (кг)",
        min_value=0.0,
        step=0.5,
        value=float(existing.get("value") or 0.0) if existing.get("status") == "ok" else 0.0,
        disabled=disabled_input,
    )

if st.button("✅ Ввести результат", type="primary"):
    db.setdefault("results", {})
    db["results"].setdefault(str(ath_id), {})

    if withdrawn:
        db["results"][str(ath_id)][score_id] = {"status": "wd", "value": 0}
    else:
        if stype == "time" and capped and cap_enabled:
            db["results"][str(ath_id)][score_id] = {"status": "capped", "value": int(value)}
        else:
            if stype == "time":
                parsed_time = parse_time_mmss(raw_time_value)
                if parsed_time is None:
                    st.error("Для TIME введи корректное значение в формате mm:ss.")
                    st.stop()
                db["results"][str(ath_id)][score_id] = {"status": "ok", "value": int(parsed_time)}
            elif stype == "reps":
                db["results"][str(ath_id)][score_id] = {"status": "ok", "value": int(value)}
            else:
                db["results"][str(ath_id)][score_id] = {"status": "ok", "value": float(value)}

    save_db(db)
    st.success("Результат сохранён.")
    st.rerun()

st.divider()
st.subheader("Ввод результата через таблицу")
st.caption("Для TIME можно вводить как mm:ss, так и без двоеточия: 534 → 5:34, 6214 → 62:14")

status_options = [STATUS_LABELS["ok"], STATUS_LABELS["wd"]]
if stype == "time" and cap_enabled:
    status_options = [STATUS_LABELS["ok"], STATUS_LABELS["capped"], STATUS_LABELS["wd"]]

rows = []
for p in participants:
    res = db.get("results", {}).get(str(p["id"]), {}).get(score_id)
    display_value = None
    if res is not None:
        if stype == "time" and res.get("status") == "ok":
            display_value = format_time_mmss(res.get("value"))
        else:
            display_value = res.get("value", None)
    rows.append({
        "athlete_id": int(p["id"]),
        "athlete": p.get("full_name", ""),
        "club": p.get("club", ""),
        "region": p.get("region", "") or p.get("city", ""),
        "status": STATUS_LABELS.get((res or {}).get("status", "ok"), "Зачтено"),
        "value": display_value,
        "preview": display_result_for_entry(sdef, res),
    })

editor_df = pd.DataFrame(rows)
value_column = st.column_config.NumberColumn("Значение", step=0.5 if stype == "weight" else 1)
if stype == "time":
    value_column = st.column_config.TextColumn("Время / повторы")

edited_df = st.data_editor(
    editor_df,
    use_container_width=True,
    hide_index=True,
    disabled=["athlete_id", "athlete", "club", "region", "preview"],
    column_config={
        "athlete_id": st.column_config.NumberColumn("ID", format="%d"),
        "athlete": st.column_config.TextColumn("Атлет"),
        "club": st.column_config.TextColumn("Клуб / команда"),
        "region": st.column_config.TextColumn("Регион"),
        "status": st.column_config.SelectboxColumn("Статус", options=status_options, required=True),
        "value": value_column,
        "preview": st.column_config.TextColumn("Будет показано"),
    },
    key=f"results_editor_{division_id}_{score_id}",
)

if st.button("💾 Сохранить таблицу результатов"):
    db.setdefault("results", {})
    for _, row in edited_df.iterrows():
        athlete_id = int(row["athlete_id"])
        status_label = str(row["status"] or "Зачтено")
        status = LABEL_TO_STATUS.get(status_label, "ok")
        raw_value = row["value"]

        db["results"].setdefault(str(athlete_id), {})

        if status == "wd":
            db["results"][str(athlete_id)][score_id] = {"status": "wd", "value": 0}
            continue

        if pd.isna(raw_value) or raw_value in ("", None):
            db["results"][str(athlete_id)].pop(score_id, None)
            continue

        if stype == "weight":
            value_to_save = float(raw_value)
        elif stype == "time":
            if status == "capped":
                value_to_save = int(float(raw_value))
            else:
                parsed_time = parse_time_mmss(raw_value)
                if parsed_time is None:
                    st.error(f"Некорректное TIME-значение у athlete_id={athlete_id}. Используй mm:ss или ввод без двоеточия.")
                    st.stop()
                value_to_save = int(parsed_time)
        else:
            value_to_save = int(float(raw_value))

        db["results"][str(athlete_id)][score_id] = {"status": status, "value": value_to_save}

    save_db(db)
    st.success("Таблица результатов сохранена.")
    st.rerun()