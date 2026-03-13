import streamlit as st
from storage import load_db, save_db
from config import DIVISIONS


def parse_mmss_to_seconds(raw: str) -> int:
    raw = str(raw or '').strip()
    if not raw:
        return 0
    if ':' not in raw:
        try:
            return max(0, int(float(raw)))
        except (TypeError, ValueError):
            return 0
    try:
        minutes, seconds = raw.split(':', 1)
        minutes_i = int(minutes)
        seconds_i = int(seconds)
        if minutes_i < 0 or seconds_i < 0:
            return 0
        return minutes_i * 60 + seconds_i
    except (TypeError, ValueError):
        return 0


def format_seconds_to_mmss(total_seconds: int) -> str:
    total_seconds = max(0, int(total_seconds or 0))
    return f"{total_seconds // 60}:{total_seconds % 60:02d}"

st.set_page_config(page_title="Results Entry", layout="wide")
st.title("🧾 Results Entry")

db = load_db()
settings = db["settings"]
scores = settings["scores"]

# --- выбираем дивизион и зачёт ---
div_titles = {d["title"]: d["id"] for d in DIVISIONS}
score_titles = {f"{s['id']} — {s['title']}": s["id"] for s in scores}

colA, colB = st.columns(2)
with colA:
    div_label = st.selectbox("Дивизион", list(div_titles.keys()))
    division_id = div_titles[div_label]
with colB:
    score_label = st.selectbox("Зачёт / Комплекс", list(score_titles.keys()))
    score_id = score_titles[score_label]

# определяем тип текущего зачёта
sdef = next(s for s in scores if s["id"] == score_id)
stype = sdef["type"]
cap_enabled = bool(sdef.get("time_cap_enabled", False))

st.info(f"Тип зачёта: **{stype}**. Time cap: **{cap_enabled}**")

# --- список атлетов этого дивизиона ---
participants = [
    p for p in db.get("participants", [])
    if p.get("division_id") == division_id and not p.get("deleted", False)
]

if not participants:
    st.warning("В этом дивизионе нет участников.")
    st.stop()

# список выбора атлета показываем с ID, чтобы не путаться
options = []
id_by_label = {}
for p in participants:
    label = f"{p['full_name']} ({p.get('club','')}, {p.get('city','')}) [ID:{p['id']}]"
    options.append(label)
    id_by_label[label] = int(p["id"])

# --- форма ввода результата ---
st.subheader("Ввод результата (после кнопки поля НЕ сбрасываем)")

# Важно: не используем st.form_submit_button с очисткой, просто пишем в db и сохраняем
ath_label = st.selectbox("Атлет", options)
ath_id = id_by_label[ath_label]

col1, col2, col3 = st.columns(3)
with col1:
    withdrawn = st.checkbox("Снялся (0 очков)", value=False)
with col2:
    capped = st.checkbox("Не уложился (только для time)", value=False, disabled=not (stype == "time" and cap_enabled))
with col3:
    st.write("")

# Поле ввода результата:
# - если withdrawn -> поле блокируем
# - если time и capped -> вводим reps (int)
# - если time и not capped -> вводим секунды (int)
# - reps -> int
# - weight -> float
disabled_input = withdrawn

value = None
if stype == "time":
    if capped and cap_enabled:
        value = st.number_input("Повторы при time cap (чем больше, тем лучше, но хуже любого времени)", min_value=0, step=1, value=0, disabled=disabled_input)
    else:
        time_input = st.text_input(
            "Время (мм:сс, чем меньше тем лучше)",
            value=format_seconds_to_mmss(0),
            disabled=disabled_input,
            help="Например: 1:32",
        )
        value = parse_mmss_to_seconds(time_input)
elif stype == "reps":
    value = st.number_input("Повторы (чем больше тем лучше)", min_value=0, step=1, value=0, disabled=disabled_input)
elif stype == "weight":
    value = st.number_input("Вес (кг, чем больше тем лучше)", min_value=0.0, step=0.5, value=0.0, disabled=disabled_input)

if st.button("✅ Ввести результат"):
    db.setdefault("results", {})
    db["results"].setdefault(str(ath_id), {})

    if withdrawn:
        db["results"][str(ath_id)][score_id] = {"status": "wd", "value": 0}
    else:
        if stype == "time" and capped and cap_enabled:
            db["results"][str(ath_id)][score_id] = {"status": "capped", "value": int(value)}
        else:
            # normal ok
            if stype in ("time", "reps"):
                db["results"][str(ath_id)][score_id] = {"status": "ok", "value": int(value)}
            else:
                db["results"][str(ath_id)][score_id] = {"status": "ok", "value": float(value)}

    save_db(db)
    st.success("Результат сохранён. Таблицы обновятся на странице Tables.")