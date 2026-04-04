import re

import streamlit as st

from storage import load_db, save_db
from config import DIVISIONS
from utils import compact_page_style, parse_time_mmss, format_time_mmss, display_result_value

st.set_page_config(page_title="Results Entry", layout="wide")
compact_page_style()
st.title("🧾 Results Entry")

st.markdown(
    """
    <style>
    .results-grid-head, .results-grid-row {
        display: grid;
        grid-template-columns: 56px minmax(220px, 2.2fr) minmax(120px, 1.3fr) minmax(150px, 1.5fr) minmax(150px, 1.2fr) minmax(140px, 1.2fr) minmax(120px, 1.2fr);
        gap: 8px;
        align-items: center;
    }
    .results-grid-head {
        font-weight: 700;
        padding: 8px 10px;
        border: 1px solid rgba(120,120,120,.25);
        border-radius: 10px;
        margin-bottom: 6px;
        background: rgba(255,255,255,.04);
    }
    .results-grid-row {
        padding: 8px 10px;
        border-bottom: 1px solid rgba(120,120,120,.18);
    }
    .results-grid-cell-muted { opacity: .82; }
    .results-grid-preview { font-weight: 600; }
    </style>
    """,
    unsafe_allow_html=True,
)


db = load_db()
settings = db["settings"]
scores = settings["scores"]

div_titles = {d["title"]: d["id"] for d in DIVISIONS}
score_titles = {f"{s['id']} — {s['title']}": s["id"] for s in scores}
STATUS_LABELS = {"ok": "Зачтено", "capped": "CAP", "wd": "Снялся"}
LABEL_TO_STATUS = {v: k for k, v in STATUS_LABELS.items()}
TIME_RE = re.compile(r"^\d+:\d{2}$")


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


def normalize_time_input(value):
    if value is None:
        return ""
    raw = str(value).strip()
    if not raw:
        return ""
    total = parse_time_mmss(raw)
    if total is None:
        return None
    pretty = format_time_mmss(total)
    if not TIME_RE.match(pretty):
        return None
    return pretty


def init_single_form_state(ctx, existing, stype, cap_enabled):
    if st.session_state.get("single_result_ctx") == ctx:
        return
    st.session_state["single_result_ctx"] = ctx
    st.session_state["single_withdrawn"] = existing.get("status") == "wd"
    st.session_state["single_capped"] = existing.get("status") == "capped"
    st.session_state["single_time"] = format_time_mmss(existing.get("value")) if existing.get("status") == "ok" and stype == "time" else ""
    st.session_state["single_cap_reps"] = int(existing.get("value") or 0) if existing.get("status") == "capped" else 0
    st.session_state["single_reps"] = int(existing.get("value") or 0) if existing.get("status") == "ok" and stype == "reps" else 0
    st.session_state["single_weight"] = float(existing.get("value") or 0.0) if existing.get("status") == "ok" and stype == "weight" else 0.0


def init_table_row_state(prefix, athlete_id, existing, stype):
    status_key = f"{prefix}_status_{athlete_id}"
    value_key = f"{prefix}_value_{athlete_id}"
    if status_key not in st.session_state:
        st.session_state[status_key] = STATUS_LABELS.get((existing or {}).get("status", "ok"), "Зачтено")
    if value_key not in st.session_state:
        if existing is None:
            st.session_state[value_key] = "" if stype == "time" else 0
        elif stype == "time":
            if existing.get("status") == "ok":
                st.session_state[value_key] = format_time_mmss(existing.get("value"))
            elif existing.get("status") == "capped":
                st.session_state[value_key] = str(int(existing.get("value") or 0))
            else:
                st.session_state[value_key] = ""
        elif stype == "weight":
            st.session_state[value_key] = float(existing.get("value") or 0.0)
        else:
            st.session_state[value_key] = int(existing.get("value") or 0)


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
ctx = f"{division_id}|{score_id}|{ath_id}"
init_single_form_state(ctx, existing, stype, cap_enabled)

col1, col2 = st.columns(2)
with col1:
    withdrawn = st.checkbox("Снялся", key="single_withdrawn")
with col2:
    capped = st.checkbox("CAP", key="single_capped", disabled=not (stype == "time" and cap_enabled))

if stype == "time":
    if withdrawn:
        st.caption("Статус 'Снялся' выбран — значение результата не требуется.")
    elif capped and cap_enabled:
        st.number_input("Повторы при CAP", min_value=0, step=1, key="single_cap_reps")
        st.caption("CAP выбран — теперь вводятся только повторения.")
    else:
        raw_time_value = st.text_input(
            "Время",
            key="single_time",
            placeholder="00:00",
            help="Строго в формате мм:сс. Например: 05:34",
        )
        preview_time = normalize_time_input(raw_time_value)
        if raw_time_value and preview_time is None:
            st.caption("Вводи только в формате мм:сс. Например: 05:34")
        else:
            st.caption(f"Формат: мм:сс{f' · будет сохранено как {preview_time}' if preview_time else ''}")
elif stype == "reps":
    st.number_input("Повторы", min_value=0, step=1, key="single_reps", disabled=withdrawn)
elif stype == "weight":
    st.number_input("Вес (кг)", min_value=0.0, step=0.5, key="single_weight", disabled=withdrawn)

if st.button("✅ Ввести результат", type="primary"):
    db.setdefault("results", {})
    db["results"].setdefault(str(ath_id), {})

    if st.session_state["single_withdrawn"]:
        db["results"][str(ath_id)][score_id] = {"status": "wd", "value": 0}
    else:
        if stype == "time" and cap_enabled and st.session_state["single_capped"]:
            db["results"][str(ath_id)][score_id] = {"status": "capped", "value": int(st.session_state["single_cap_reps"])}
        else:
            if stype == "time":
                normalized = normalize_time_input(st.session_state.get("single_time", ""))
                if normalized is None or not normalized:
                    st.error("Для TIME введи значение строго в формате мм:сс. Например: 05:34")
                    st.stop()
                db["results"][str(ath_id)][score_id] = {"status": "ok", "value": int(parse_time_mmss(normalized))}
            elif stype == "reps":
                db["results"][str(ath_id)][score_id] = {"status": "ok", "value": int(st.session_state["single_reps"])}
            else:
                db["results"][str(ath_id)][score_id] = {"status": "ok", "value": float(st.session_state["single_weight"])}

    save_db(db)
    st.success("Результат сохранён.")
    st.rerun()

st.divider()
st.subheader("Ввод результата таблицей")
if stype == "time":
    st.caption("Для TIME: Зачтено = время мм:сс, CAP = повторы, Снялся = пустое поле.")

prefix = f"table_{division_id}_{score_id}"
st.markdown(
    '<div class="results-grid-head"><div>#</div><div>Участник</div><div>Клуб</div><div>Регион</div><div>Статус</div><div>Значение</div><div>Будет показано</div></div>',
    unsafe_allow_html=True,
)

status_options = [STATUS_LABELS["ok"], STATUS_LABELS["wd"]]
if stype == "time" and cap_enabled:
    status_options = [STATUS_LABELS["ok"], STATUS_LABELS["capped"], STATUS_LABELS["wd"]]

for idx, p in enumerate(participants, start=1):
    athlete_id = int(p["id"])
    existing_row = db.get("results", {}).get(str(athlete_id), {}).get(score_id)
    init_table_row_state(prefix, athlete_id, existing_row, stype)
    status_key = f"{prefix}_status_{athlete_id}"
    value_key = f"{prefix}_value_{athlete_id}"

    current_status_label = st.session_state.get(status_key, "Зачтено")
    current_status = LABEL_TO_STATUS.get(current_status_label, "ok")

    cols = st.columns([0.55, 2.2, 1.35, 1.55, 1.25, 1.3, 1.4])
    cols[0].markdown(str(idx))
    cols[1].markdown(f"**{p.get('full_name','')}**")
    cols[2].markdown(p.get("club", "") or "—")
    cols[3].markdown((p.get("region", "") or p.get("city", "")) or "—")

    cols[4].selectbox(
        "Статус",
        status_options,
        key=status_key,
        label_visibility="collapsed",
    )

    if stype == "time":
        if current_status == "wd":
            cols[5].text_input("Значение", value="", key=f"{value_key}_wd", disabled=True, label_visibility="collapsed")
            preview = "Снялся"
        elif current_status == "capped":
            current_raw = st.session_state.get(value_key, "")
            try:
                current_num = int(float(current_raw)) if str(current_raw).strip() else 0
            except Exception:
                current_num = 0
            new_num = cols[5].number_input("Значение", min_value=0, step=1, value=current_num, key=f"{value_key}_cap", label_visibility="collapsed")
            st.session_state[value_key] = str(int(new_num))
            preview = f"CAP {int(new_num)}"
        else:
            current_text = st.session_state.get(value_key, "")
            new_text = cols[5].text_input("Значение", value=current_text, placeholder="00:00", key=f"{value_key}_time", label_visibility="collapsed")
            st.session_state[value_key] = new_text
            normalized = normalize_time_input(new_text)
            preview = normalized if normalized else ("" if not new_text else "Ошибка")
    elif stype == "weight":
        current_raw = st.session_state.get(value_key, 0.0)
        try:
            current_num = float(current_raw)
        except Exception:
            current_num = 0.0
        new_num = cols[5].number_input("Значение", min_value=0.0, step=0.5, value=current_num, key=f"{value_key}_weight", label_visibility="collapsed")
        st.session_state[value_key] = new_num
        preview = display_result_value(sdef, new_num)
    else:
        current_raw = st.session_state.get(value_key, 0)
        try:
            current_num = int(float(current_raw))
        except Exception:
            current_num = 0
        new_num = cols[5].number_input("Значение", min_value=0, step=1, value=current_num, key=f"{value_key}_reps", label_visibility="collapsed")
        st.session_state[value_key] = new_num
        preview = display_result_value(sdef, new_num)

    cols[6].markdown(preview or "—")
    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

if st.button("💾 Сохранить таблицу результатов"):
    db.setdefault("results", {})
    errors = []

    for p in participants:
        athlete_id = int(p["id"])
        athlete_name = p.get("full_name") or str(athlete_id)
        status_key = f"{prefix}_status_{athlete_id}"
        value_key = f"{prefix}_value_{athlete_id}"
        status_label = st.session_state.get(status_key, "Зачтено")
        status = LABEL_TO_STATUS.get(status_label, "ok")
        raw_value = st.session_state.get(value_key, "")

        db["results"].setdefault(str(athlete_id), {})

        if status == "wd":
            db["results"][str(athlete_id)][score_id] = {"status": "wd", "value": 0}
            continue

        if raw_value in ("", None):
            db["results"][str(athlete_id)].pop(score_id, None)
            continue

        if stype == "time":
            if status == "capped":
                try:
                    value_to_save = int(float(raw_value))
                except (TypeError, ValueError):
                    errors.append(f"{athlete_name}: для CAP введи целое число повторов")
                    continue
            else:
                normalized = normalize_time_input(raw_value)
                if normalized is None or not normalized:
                    errors.append(f"{athlete_name}: время должно быть в формате мм:сс")
                    continue
                value_to_save = int(parse_time_mmss(normalized))
        elif stype == "weight":
            try:
                value_to_save = float(raw_value)
            except (TypeError, ValueError):
                errors.append(f"{athlete_name}: вес должен быть числом")
                continue
        else:
            try:
                value_to_save = int(float(raw_value))
            except (TypeError, ValueError):
                errors.append(f"{athlete_name}: повторы должны быть числом")
                continue

        db["results"][str(athlete_id)][score_id] = {"status": status, "value": value_to_save}

    if errors:
        st.error("Не сохранил таблицу. Исправь ошибки:\n- " + "\n- ".join(errors[:12]))
        st.stop()

    save_db(db)
    st.success("Таблица результатов сохранена.")
    st.rerun()
