import subprocess
import sys
import streamlit as st

st.set_page_config(page_title="Publish", layout="wide")
st.title("🚀 Publish (GitHub Pages)")

st.write(
    "Эта страница:\n"
    "1) Соберёт docs/results.json и docs/flags\n"
    "2) Закоммитит только папку docs\n"
    "3) Проверит, что Git не завис в merge/rebase\n"
    "4) Сделает fetch и push только если это безопасно\n"
    "5) Покажет подробный лог публикации\n\n"
    "Важно: страница не делает pull/rebase автоматически, чтобы не откатить рабочий проект."
)

if "publish_log" not in st.session_state:
    st.session_state.publish_log = ""

if st.button("🚀 Publish now", type="primary"):
    with st.spinner("Публикация..."):
        proc = subprocess.run(
            [sys.executable, "-m", "publish.github_push"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        st.session_state.publish_log = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        if proc.returncode == 0:
            st.success("Опубликовано. GitHub Pages обновится через несколько секунд или минуту.")
        else:
            st.error("Публикация остановлена. Причина ниже в логе. Сам проект при этом не откатывается.")

st.subheader("Лог публикации")
st.code(st.session_state.publish_log or "Лог пока пуст.", language="bash")
