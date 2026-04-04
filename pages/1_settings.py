import hashlib

import streamlit as st
from PIL import Image

from storage import (
    load_db,
    save_db,
    default_display_settings,
    clear_results,
    clear_all_data,
    default_team_scoring,
    default_workout_structure,
    workout_code_list,
    default_workouts_for_structure,
)
from config import DIVISIONS, DATA_FLAGS_DIR, MAX_FLAG_UPLOAD_BYTES, MAX_FLAG_DIMENSION
from utils import compact_page_style

st.set_page_config(page_title="Settings", layout="wide")
compact_page_style()
st.title("⚙️ Settings")

WORKOUT_TYPES = ["", "FOR TIME", "AMRAP", "EMOM", "INTERVALS", "STRENGTH", "SKILL", "CHIPPER", "OTHER"]
DIVISION_LABELS = {d["id"]: d["title"] for d in DIVISIONS}


def save_club_flag_image(flag_file, club_name: str) -> str:
    img_bytes = flag_file.read()
    if not img_bytes:
        raise ValueError("Файл флага пустой.")
    if len(img_bytes) > MAX_FLAG_UPLOAD_BYTES:
        raise ValueError(f"Файл слишком большой. Максимум {MAX_FLAG_UPLOAD_BYTES // 1024 // 1024} MB.")

    flag_file.seek(0)
    try:
        img = Image.open(flag_file)
        img.load()
    except Exception as exc:
        raise ValueError(f"Не удалось прочитать изображение: {exc}") from exc

    img = img.convert("RGBA")
    img.thumbnail((MAX_FLAG_DIMENSION, MAX_FLAG_DIMENSION))
    DATA_FLAGS_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.md5(club_name.encode("utf-8")).hexdigest()[:12]
    out_path = DATA_FLAGS_DIR / f"club_{digest}.png"
    img.save(out_path, format="PNG")
    return str(out_path)


def club_option_label(club_name: str, club_settings: dict) -> str:
    info = club_settings.get(club_name, {}) if isinstance(club_settings, dict) else {}
    city = str(info.get("city") or "").strip()
    return f"{club_name} — {city}" if city else club_name


def structure_rows_from_inputs(total_count: int) -> list[dict]:
    rows: list[dict] = []
    for i in range(1, total_count + 1):
        raw_parts = st.session_state.get(f"workout_parts_{i}", "")
        parts = []
        for token in [x.strip().upper() for x in str(raw_parts).split(",")]:
            if token and token not in parts:
                parts.append(token)
        rows.append({"base": f"WOD{i}", "parts": parts or [""]})
    return rows


def format_structure_preview(structure: list[dict]) -> str:
    codes = workout_code_list(structure)
    return ", ".join(codes) if codes else "—"


def render_workouts_summary(settings: dict) -> None:
    structure = settings.get("workout_structure") or default_workout_structure()
    workouts = settings.get("workouts") or default_workouts_for_structure(structure)
    codes = workout_code_list(structure)

    st.markdown("### Сохранённые комплексы")
    for div in DIVISIONS:
        div_id = div["id"]
        st.markdown(f"**{div['title']}**")
        rows = []
        div_workouts = workouts.get(div_id, {}) if isinstance(workouts, dict) else {}
        for code in codes:
            item = div_workouts.get(code, {}) if isinstance(div_workouts.get(code), dict) else {}
            rows.append({
                "Код": code,
                "Имя": item.get("label") or code,
                "Тип": item.get("type") or "—",
                "Лимит": item.get("time_cap") or "—",
                "Описание": item.get("description") or "—",
            })
        st.dataframe(rows, width='stretch', hide_index=True)


db = load_db()
settings = db["settings"]

if "confirm_clear_results" not in st.session_state:
    st.session_state.confirm_clear_results = False
if "confirm_clear_all" not in st.session_state:
    st.session_state.confirm_clear_all = False

settings.setdefault("display", default_display_settings())
settings.setdefault("clubs", [])
settings.setdefault("club_settings", {})
settings.setdefault("team_scoring", default_team_scoring())
settings.setdefault("tv_scene_duration_sec", 10)
settings.setdefault("workout_structure", default_workout_structure())
settings.setdefault("workouts", default_workouts_for_structure(settings["workout_structure"]))

st.subheader("Лимиты участников по дивизионам")
limits = settings["division_limits"]
changed = False

cols = st.columns(4)
for i, d in enumerate(DIVISIONS):
    with cols[i]:
        key = d["id"]
        cur = int(limits.get(key, 0))
        new_val = st.number_input(d["title"], min_value=0, step=1, value=cur, key=f"limit_{key}")
        if int(new_val) != cur:
            limits[key] = int(new_val)
            changed = True

st.divider()
st.subheader("Клубы")
club_list = settings.setdefault("clubs", [])
club_text = st.text_area(
    "Список клубов",
    value="\n".join(club_list),
    height=160,
    help="По одному клубу в строке. Эти клубы будут доступны в выпадающем списке при добавлении и редактировании атлета.",
)
parsed_clubs = []
seen = set()
for line in club_text.splitlines():
    name = line.strip()
    if not name:
        continue
    key = name.casefold()
    if key in seen:
        continue
    seen.add(key)
    parsed_clubs.append(name)
parsed_clubs.sort(key=lambda x: x.casefold())
if parsed_clubs != club_list:
    settings["clubs"] = parsed_clubs
    changed = True

club_settings = settings.setdefault("club_settings", {})
for club_name in settings["clubs"]:
    club_settings.setdefault(club_name, {"city": "", "flag_path": None})
for club_name in list(club_settings.keys()):
    if club_name not in settings["clubs"]:
        club_settings.pop(club_name, None)
        changed = True

st.markdown("### Настройки введённых клубов")
if settings["clubs"]:
    selected_club = st.selectbox(
        "Выбери клуб",
        settings["clubs"],
        format_func=lambda name: club_option_label(name, club_settings),
    )
    club_info = club_settings.setdefault(selected_club, {"city": "", "flag_path": None})

    c1, c2 = st.columns([1.3, 1.0])
    with c1:
        club_city = st.text_input("Город / регион клуба", value=club_info.get("city", ""))
        if club_city != club_info.get("city", ""):
            club_info["city"] = club_city.strip()
            changed = True
    with c2:
        club_flag_file = st.file_uploader(
            "Флаг клуба",
            type=["png", "jpg", "jpeg"],
            key="club_flag_uploader",
        )
        if club_info.get("flag_path"):
            try:
                st.image(club_info["flag_path"], width=52)
            except Exception:
                st.caption("Текущий флаг недоступен")
        else:
            st.caption("Флаг пока не загружен")

    action_cols = st.columns(2)
    if action_cols[0].button("Сохранить настройки клуба", type="secondary"):
        if club_flag_file is not None:
            try:
                club_info["flag_path"] = save_club_flag_image(club_flag_file, selected_club)
            except ValueError as exc:
                st.error(str(exc))
                st.stop()
        save_db(db)
        st.success("Настройки клуба обновлены.")
        st.rerun()
    if action_cols[1].button("Удалить флаг клуба"):
        club_info["flag_path"] = None
        save_db(db)
        st.warning("Флаг клуба удалён.")
        st.rerun()
else:
    st.info("Сначала добавь хотя бы один клуб в список выше.")

st.divider()
st.subheader("Клубный зачёт")
team_scoring = settings.setdefault("team_scoring", default_team_scoring())
priority_score_id = str(team_scoring.get("priority_score_id") or "WOD3")
score_ids = [s["id"] for s in settings.get("scores", [])]
if priority_score_id not in score_ids and score_ids:
    priority_score_id = score_ids[-1]
    team_scoring["priority_score_id"] = priority_score_id
    changed = True

c1, c2 = st.columns([1, 1])
with c1:
    new_enabled = st.checkbox("Включить клубный зачёт", value=bool(team_scoring.get("enabled", True)))
    if new_enabled != bool(team_scoring.get("enabled", True)):
        team_scoring["enabled"] = new_enabled
        changed = True
with c2:
    new_priority = st.selectbox("Приоритетный комплекс", score_ids, index=score_ids.index(priority_score_id) if priority_score_id in score_ids else 0)
    if new_priority != priority_score_id:
        team_scoring["priority_score_id"] = new_priority
        changed = True

places_cfg = team_scoring.setdefault("places", [1, 2, 3])
place_cols = st.columns(3)
for idx, place in enumerate((1, 2, 3)):
    with place_cols[idx]:
        checked = place in places_cfg
        new_checked = st.checkbox(f"Начислять за {place} место", value=checked, key=f"team_place_{place}")
        if new_checked and place not in places_cfg:
            places_cfg.append(place)
            places_cfg.sort()
            changed = True
        if not new_checked and place in places_cfg:
            places_cfg.remove(place)
            changed = True

st.caption("Ниже задаются очки клубного зачёта за призовые места в каждой индивидуальной категории.")
for div in DIVISIONS:
    div_id = div["id"]
    cur_map = team_scoring.setdefault("division_points", {}).setdefault(div_id, {"1": 0, "2": 0, "3": 0})
    st.markdown(f"**{div['title']}**")
    cols = st.columns(3)
    for idx, place in enumerate((1, 2, 3)):
        cur_val = int(cur_map.get(str(place), 0))
        with cols[idx]:
            new_val = st.number_input(f"{place} место", min_value=0, step=1, value=cur_val, key=f"team_pts_{div_id}_{place}")
        if int(new_val) != cur_val:
            cur_map[str(place)] = int(new_val)
            changed = True

st.divider()
st.subheader("Настройка зачётов")
score_rows = settings["scores"]
for s in score_rows:
    st.markdown(f"### {s['id']} — {s['title']}")
    c1, c2 = st.columns(2)
    with c1:
        new_type = st.selectbox(
            "Тип",
            ["time", "reps", "weight"],
            index=["time", "reps", "weight"].index(s["type"]),
            key=f"type_{s['id']}",
        )
        if new_type != s["type"]:
            s["type"] = new_type
            changed = True
    with c2:
        new_cap = st.checkbox(
            "Разрешить Time cap (только для time)",
            value=bool(s.get("time_cap_enabled", False)),
            key=f"cap_{s['id']}",
        )
        if new_cap != bool(s.get("time_cap_enabled", False)):
            s["time_cap_enabled"] = bool(new_cap)
            changed = True

st.divider()
st.subheader("Комплексы / WOD")
st.caption("Это отдельная сущность для описания комплексов. Сначала задаётся структура WOD, потом вручную заполняются комплексы по каждой категории и полу.")

structure = settings.setdefault("workout_structure", default_workout_structure())
workouts = settings.setdefault("workouts", default_workouts_for_structure(structure))

st.markdown("### Структура комплексов")
current_count = len(structure)
new_count = st.number_input("Количество базовых WOD", min_value=1, max_value=8, value=current_count, step=1)
for i in range(1, int(new_count) + 1):
    existing_row = structure[i - 1] if i - 1 < len(structure) else {"base": f"WOD{i}", "parts": [""]}
    existing_parts = ", ".join([p for p in existing_row.get("parts", [""]) if p])
    st.text_input(
        f"Дробление для WOD{i}",
        value=existing_parts,
        key=f"workout_parts_{i}",
        help="Оставь пустым для обычного WOD. Если нужен разбор, введи буквы через запятую: A,B",
    )

preview_structure = structure_rows_from_inputs(int(new_count))
st.caption(f"Будут доступны коды: {format_structure_preview(preview_structure)}")

if st.button("Сохранить структуру комплексов", type="secondary"):
    settings["workout_structure"] = preview_structure
    settings["workouts"] = default_workouts_for_structure(preview_structure) | {
        div_id: {
            **default_workouts_for_structure(preview_structure).get(div_id, {}),
            **(workouts.get(div_id, {}) if isinstance(workouts.get(div_id), dict) else {}),
        }
        for div_id in DIVISION_LABELS
    }
    save_db(db)
    st.success("Структура комплексов сохранена.")
    st.rerun()

st.markdown("### Ввод комплекса")
structure = settings.setdefault("workout_structure", default_workout_structure())
workouts = settings.setdefault("workouts", default_workouts_for_structure(structure))
code_options = workout_code_list(structure)
selected_division = st.selectbox("Категория и пол", list(DIVISION_LABELS.keys()), format_func=lambda x: DIVISION_LABELS[x], key="workout_division_select")
selected_code = st.selectbox("WOD", code_options, key="workout_code_select")
entry = workouts.setdefault(selected_division, {}).setdefault(selected_code, {
    "label": selected_code,
    "type": "",
    "time_cap": "",
    "description": "",
})

wc1, wc2 = st.columns(2)
with wc1:
    workout_label = st.text_input("Обозначение / имя", value=entry.get("label") or selected_code, key="workout_label_input")
with wc2:
    current_type = entry.get("type") or ""
    workout_type = st.selectbox("Тип комплекса", WORKOUT_TYPES, index=WORKOUT_TYPES.index(current_type) if current_type in WORKOUT_TYPES else 0, key="workout_type_input")

wc3, = st.columns(1)
with wc3:
    workout_cap = st.text_input("Лимит времени", value=entry.get("time_cap") or "", key="workout_cap_input", placeholder="Например: 10:00 или 12 мин")

workout_description = st.text_area("Текст описания", value=entry.get("description") or "", key="workout_description_input", height=120)

wbtn1, wbtn2 = st.columns(2)
if wbtn1.button("Сохранить комплекс", type="secondary"):
    workouts.setdefault(selected_division, {})[selected_code] = {
        "label": workout_label.strip() or selected_code,
        "type": workout_type.strip(),
        "time_cap": workout_cap.strip(),
        "description": workout_description.strip(),
    }
    save_db(db)
    st.success("Комплекс сохранён.")
    st.rerun()
if wbtn2.button("Очистить комплекс"):
    workouts.setdefault(selected_division, {})[selected_code] = {
        "label": selected_code,
        "type": "",
        "time_cap": "",
        "description": "",
    }
    save_db(db)
    st.warning("Комплекс очищен.")
    st.rerun()

render_workouts_summary(settings)

st.divider()
st.subheader("ТВ-ротация")
current_tv_duration = int(settings.get("tv_scene_duration_sec", 10))
new_tv_duration = st.slider(
    "Время смены экранов ТВ (сек)",
    min_value=3,
    max_value=60,
    value=current_tv_duration,
    step=1,
    help="Одна общая настройка для ротации экранов ТВ.",
)
if new_tv_duration != current_tv_duration:
    settings["tv_scene_duration_sec"] = int(new_tv_duration)
    changed = True

st.divider()
st.subheader("Ручная настройка отображения экранов")
st.caption("Эти настройки попадают в public-экраны после Publish и помогают уместить больше информации на ТВ и mobile.")

display = settings["display"]
display_labels = {
    "section_title_size": "Размер заголовков разделов",
    "card_title_size": "Размер заголовков блоков",
    "table_text_size": "Размер текста таблиц",
    "meta_text_size": "Размер вторичного текста",
    "row_height": "Вертикальный отступ строк",
    "block_gap": "Отступы между блоками",
    "container_scale": "Масштаб контейнеров",
}
display_ranges = {
    "section_title_size": (14, 36, 1),
    "card_title_size": (12, 30, 1),
    "table_text_size": (9, 22, 1),
    "meta_text_size": (8, 18, 1),
    "row_height": (2, 14, 1),
    "block_gap": (4, 24, 1),
    "container_scale": (0.8, 1.2, 0.01),
}

for screen_key, title in (("main", "Основные экраны"), ("mobile", "Мобильный экран")):
    st.markdown(f"### {title}")
    cols = st.columns(2)
    screen_settings = display.setdefault(screen_key, default_display_settings()[screen_key])
    for idx, (key, label) in enumerate(display_labels.items()):
        col = cols[idx % 2]
        min_v, max_v, step = display_ranges[key]
        current = screen_settings.get(key, default_display_settings()[screen_key][key])
        with col:
            if isinstance(step, float):
                new_value = st.slider(label, min_value=float(min_v), max_value=float(max_v), value=float(current), step=float(step), key=f"display_{screen_key}_{key}")
            else:
                new_value = st.slider(label, min_value=int(min_v), max_value=int(max_v), value=int(current), step=int(step), key=f"display_{screen_key}_{key}")
        if new_value != current:
            screen_settings[key] = new_value
            changed = True

    if st.button(f"Сбросить настройки: {title}", key=f"reset_display_{screen_key}"):
        display[screen_key] = default_display_settings()[screen_key].copy()
        save_db(db)
        st.success(f"Настройки '{title}' сброшены.")
        st.rerun()

st.divider()
st.subheader("Сервисные действия")
left, right = st.columns(2)
with left:
    st.warning("Очистить только результаты: атлеты, клубы и заходы останутся.")
    if not st.session_state.confirm_clear_results:
        if st.button("🧹 Очистить результаты", key="clear_results_btn"):
            st.session_state.confirm_clear_results = True
            st.rerun()
    else:
        st.error("Подтверди очистку результатов. Это действие нельзя отменить.")
        confirm_cols = st.columns(2)
        if confirm_cols[0].button("✅ Да, очистить результаты", key="confirm_clear_results_yes"):
            clear_results(db)
            save_db(db)
            st.session_state.confirm_clear_results = False
            st.success("Результаты очищены. Атлеты, клубы и заходы сохранены.")
            st.rerun()
        if confirm_cols[1].button("❌ Отмена", key="confirm_clear_results_no"):
            st.session_state.confirm_clear_results = False
            st.rerun()
with right:
    st.error("Полное удаление данных: атлеты, результаты и заходы будут очищены.")
    if not st.session_state.confirm_clear_all:
        if st.button("🗑️ Удалить всё", key="clear_all_btn"):
            st.session_state.confirm_clear_all = True
            st.rerun()
    else:
        st.error("Подтверди полное удаление. Это действие нельзя отменить.")
        confirm_cols = st.columns(2)
        if confirm_cols[0].button("✅ Да, удалить всё", key="confirm_clear_all_yes"):
            clear_all_data(db)
            save_db(db)
            st.session_state.confirm_clear_all = False
            st.success("Все данные очищены.")
            st.rerun()
        if confirm_cols[1].button("❌ Отмена", key="confirm_clear_all_no"):
            st.session_state.confirm_clear_all = False
            st.rerun()

st.divider()
if st.button("💾 Сохранить настройки", type="primary"):
    save_db(db)
    st.success("Настройки сохранены.")
elif changed:
    st.warning("Есть изменения. Нажми 'Сохранить настройки'.")
