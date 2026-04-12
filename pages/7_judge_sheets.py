from __future__ import annotations

import streamlit as st

from config import DIVISIONS
from judge_sheets import build_judge_sheets_pdf_bytes, count_rows_by_division, selected_divisions
from storage import load_db
from utils import compact_page_style

st.set_page_config(page_title="Judge Sheets", page_icon="📝", layout="wide")
compact_page_style()

st.title("📝 Судейские бланки")
st.caption("Отдельный печатный бланк на каждого атлета. Данные автоматически берутся из HEATS.")

WOD_OPTIONS = ["WOD1", "WOD2", "WOD3"]
DIVISION_TITLE_MAP = {item["id"]: item["title"] for item in DIVISIONS}
ALL_DIVISIONS = [item["id"] for item in DIVISIONS]


def default_divisions_for_wod(db, wod_id: str):
    available = selected_divisions(db, wod_id, ALL_DIVISIONS)
    return available or ALL_DIVISIONS


db = load_db()

c1, c2 = st.columns([1, 1.4])
with c1:
    wod_id = st.selectbox("Комплекс", WOD_OPTIONS, index=0)
with c2:
    chosen_divisions = st.multiselect(
        "Категории",
        ALL_DIVISIONS,
        default=default_divisions_for_wod(db, wod_id),
        format_func=lambda x: DIVISION_TITLE_MAP.get(x, x),
    )

if not chosen_divisions:
    st.warning("Выбери хотя бы одну категорию.")
    st.stop()

summary = count_rows_by_division(db, wod_id, chosen_divisions)
active_summary = [row for row in summary if row["count"] > 0]

if not active_summary:
    st.warning("Для выбранного комплекса и категорий нет назначенных heats.")
    st.stop()

st.markdown("### Что попадёт в PDF")
cols = st.columns(min(4, max(1, len(active_summary))))
for idx, row in enumerate(active_summary):
    with cols[idx % len(cols)]:
        st.metric(row["division_title"], f"{row['count']} бланк.")

st.info(
    "PDF формируется без изменения базы: модуль только читает участников и heats, "
    "подставляет ФИО, категорию, заход и дорожку в печатные шаблоны."
)

filename = f"judge_sheets_{wod_id}_{'_'.join(chosen_divisions)}.pdf"

if st.button("Сформировать PDF", type="primary"):
    try:
        pdf_bytes = build_judge_sheets_pdf_bytes(db, wod_id, chosen_divisions)
    except Exception as exc:
        st.error(f"Не удалось сформировать PDF: {exc}")
    else:
        st.success(f"PDF готов: {sum(row['count'] for row in active_summary)} бланков.")
        st.download_button(
            "Скачать PDF",
            data=pdf_bytes,
            file_name=filename,
            mime="application/pdf",
            use_container_width=True,
        )
        with st.expander("Что входит в шаблон"):
            st.write(
                "- отдельная страница на каждого атлета;\n"
                "- автоматическая подстановка категории, захода, дорожки и ФИО;\n"
                "- пустое поле судьи;\n"
                "- зоны для галочек и заметок;\n"
                "- итоговый блок для времени, repetitions, статуса и подписи."
            )
