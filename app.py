import streamlit as st

st.set_page_config(page_title="CrossFit Admin", layout="wide")

st.title("CrossFit — Админка (локально)")
st.write("Открой нужный раздел:")

st.page_link("pages/1_settings.py", label="⚙️ Настройки", icon="⚙️")
st.page_link("pages/2_participants.py", label="👥 Участники", icon="👥")
st.page_link("pages/3_results_entry.py", label="🧾 Ввод результатов", icon="🧾")
st.page_link("pages/4_tables.py", label="📊 Таблицы", icon="📊")
st.page_link("pages/5_heats.py", label="🏁 Заходы", icon="🏁")
st.page_link("pages/6_publish.py", label="🚀 Публикация (GitHub Pages)", icon="🚀")
st.page_link("pages/7_judge_sheets.py", label="📝 Судейские бланки", icon="📝")

st.divider()
st.info("Админка работает локально. Публичная витрина обновляется после кнопки Publish.")