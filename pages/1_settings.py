import streamlit as st

from storage import load_db, save_db, default_display_settings, clear_results, clear_all_data
from config import DIVISIONS
from utils import compact_page_style

st.set_page_config(page_title="Settings", layout="wide")
compact_page_style()
st.title("⚙️ Settings")

db = load_db()
settings = db["settings"]
display = settings.setdefault("display", default_display_settings())
changed = False

st.subheader("Лимиты участников по дивизионам")
limits = settings["division_limits"]
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


def slider_block(title: str, key: str, specs: list[tuple[str, str, int, int, float, int | float]]):
    global changed
    st.divider()
    st.subheader(title)
    target = display.setdefault(key, default_display_settings()[key])
    c1, c2 = st.columns(2)
    halves = [specs[: (len(specs) + 1) // 2], specs[(len(specs) + 1) // 2 :]]
    for col, items in zip((c1, c2), halves):
        with col:
            for label, field, min_v, max_v, default_v, step in items:
                cur = target.get(field, default_v)
                new_val = st.slider(label, min_value=min_v, max_value=max_v, value=cur, step=step, key=f"{key}_{field}")
                if new_val != cur:
                    target[field] = new_val
                    changed = True


slider_block(
    "Настройки TV / основных экранов",
    "main",
    [
        ("Размер заголовков разделов", "section_title_size", 20, 42, 30, 1),
        ("Размер заголовков карточек", "card_title_size", 16, 34, 24, 1),
        ("Размер текста таблиц", "table_text_size", 12, 24, 18, 1),
        ("Размер вторичного текста", "meta_text_size", 10, 18, 14, 1),
        ("Высота строк", "row_height", 24, 52, 36, 1),
        ("Отступы между блоками", "block_gap", 4, 24, 12, 1),
        ("Масштаб контейнеров", "container_scale", 0.8, 1.15, 1.0, 0.01),
    ],
)

slider_block(
    "Настройки мобильного экрана",
    "mobile",
    [
        ("Размер заголовков разделов", "section_title_size", 14, 28, 18, 1),
        ("Размер заголовков карточек", "card_title_size", 12, 24, 16, 1),
        ("Размер текста таблиц", "table_text_size", 10, 18, 12, 1),
        ("Размер вторичного текста", "meta_text_size", 9, 16, 11, 1),
        ("Высота строк", "row_height", 20, 42, 28, 1),
        ("Отступы между блоками", "block_gap", 4, 20, 8, 1),
        ("Масштаб контейнеров", "container_scale", 0.8, 1.15, 1.0, 0.01),
        ("Размер заголовка захода", "heat_title_font_size", 12, 24, 16, 1),
        ("Размер имени атлета в заходе", "heat_name_font_size", 10, 20, 13, 1),
        ("Размер номера дорожки", "heat_lane_font_size", 10, 18, 13, 1),
        ("Ширина карточки захода", "heat_card_width", 140, 280, 180, 10),
    ],
)

st.divider()
st.subheader("Сервисные действия")
service1, service2 = st.columns(2)
with service1:
    if st.button("🧹 Очистить результаты", use_container_width=True):
        clear_results(db)
        save_db(db)
        st.success("Результаты очищены. Атлеты, клубы и заходы сохранены.")
        st.rerun()
with service2:
    if st.button("🗑️ Удалить всё", use_container_width=True):
        cleared = clear_all_data(db)
        save_db(cleared)
        st.success("Все участники, результаты и заходы удалены. Настройки сохранены.")
        st.rerun()

st.divider()
if st.button("💾 Save Settings", type="primary"):
    save_db(db)
    st.success("Сохранено.")
elif changed:
    st.warning("Есть изменения. Нажми Save Settings.")
