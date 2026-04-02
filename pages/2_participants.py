import streamlit as st
from PIL import Image
from io import BytesIO
from datetime import date

from storage import load_db, save_db, next_participant_id, count_participants_in_division, delete_participant
from config import DATA_FLAGS_DIR, MAX_FLAG_UPLOAD_BYTES, MAX_FLAG_DIMENSION
from utils import compact_page_style, parse_birth_date, birth_date_to_storage, display_birth_date, participant_age

st.set_page_config(page_title="Participants", layout="wide")
compact_page_style()
st.title("👥 Participants")

db = load_db()
settings = db["settings"]
clubs = settings.get("clubs", [])


def resolve_division_id(sex_val: str, cat_val: str) -> str:
    if cat_val == "BEGSCAL" and sex_val == "M":
        return "BEGSCAL_M"
    if cat_val == "BEGSCAL" and sex_val == "F":
        return "BEGSCAL_F"
    if cat_val == "INT" and sex_val == "M":
        return "INT_M"
    return "INT_F"


def save_flag_image(flag_file, pid: int) -> str:
    img_bytes = flag_file.read()
    if len(img_bytes) > MAX_FLAG_UPLOAD_BYTES:
        max_mb = round(MAX_FLAG_UPLOAD_BYTES / 1024 / 1024, 2)
        raise ValueError(f"Файл флага слишком большой. Максимум {max_mb} MB.")

    try:
        img = Image.open(BytesIO(img_bytes))
        img.verify()
        img = Image.open(BytesIO(img_bytes)).convert("RGBA")
    except Exception as exc:
        raise ValueError(f"Не удалось обработать картинку флага: {exc}") from exc

    img.thumbnail((MAX_FLAG_DIMENSION, MAX_FLAG_DIMENSION))
    out_path = DATA_FLAGS_DIR / f"athlete_{pid}.png"
    img.save(out_path, format="PNG", optimize=True)
    return str(out_path.as_posix())


def normalize_club_choice(choice: str) -> str:
    return "" if choice == "—" else choice


def club_select_options():
    return ["—"] + clubs


def sort_value(participant: dict, sort_key: str):
    if sort_key == "id":
        return int(participant.get("id") or 0)
    if sort_key == "full_name":
        return str(participant.get("full_name") or "").lower()
    if sort_key == "birth_date":
        birth = parse_birth_date(participant.get("birth_date"))
        return birth or date(2100, 1, 1)
    if sort_key == "sex":
        return str(participant.get("sex") or "")
    if sort_key == "category":
        return str(participant.get("category") or "")
    if sort_key == "division_id":
        return str(participant.get("division_id") or "")
    if sort_key == "region":
        return str(participant.get("region") or participant.get("city") or "").lower()
    if sort_key == "club":
        return str(participant.get("club") or "").lower()
    if sort_key == "age":
        age = participant_age(participant)
        if age in (None, ""):
            return 999
        return int(age)
    return str(participant.get(sort_key) or "").lower()


st.subheader("Добавить участника")
with st.form("add_participant"):
    c1, c2, c3 = st.columns(3)
    with c1:
        full_name = st.text_input("Фамилия Имя")
        sex = st.selectbox("Пол", ["M", "F"], format_func=lambda x: "МУЖЧИНЫ" if x == "M" else "ЖЕНЩИНЫ")
        birth_date = st.date_input(
            "Дата рождения",
            format="DD.MM.YYYY",
            value=date(2000, 1, 1),
            min_value=date(1950, 1, 1),
            max_value=date.today(),
        )
    with c2:
        category = st.selectbox("Категория", ["BEGSCAL", "INT"])
        region = st.text_input("Регион")
    with c3:
        club_choice = st.selectbox("Клуб", club_select_options())
        flag_file = st.file_uploader(
            f"Флаг (PNG/JPG, до {MAX_FLAG_UPLOAD_BYTES // 1024 // 1024} MB)",
            type=["png", "jpg", "jpeg"],
        )

    submitted = st.form_submit_button("➕ Добавить")

if submitted:
    name = (full_name or "").strip()
    if not name:
        st.error("ФИО пустое.")
    elif not birth_date_to_storage(birth_date):
        st.error("Укажи дату рождения.")
    else:
        division_id = resolve_division_id(sex, category)
        limit = int(db["settings"]["division_limits"].get(division_id, 0))
        current = count_participants_in_division(db, division_id)

        if limit > 0 and current >= limit:
            st.error(f"Лимит для {division_id} = {limit}. Сейчас уже {current}. Добавление запрещено.")
        else:
            pid = next_participant_id(db)
            flag_path = None
            if flag_file is not None:
                try:
                    flag_path = save_flag_image(flag_file, pid)
                except ValueError as exc:
                    st.error(str(exc))
                    st.stop()

            db["participants"].append({
                "id": pid,
                "full_name": name,
                "sex": sex,
                "birth_date": birth_date_to_storage(birth_date),
                "age": 0,
                "category": category,
                "division_id": division_id,
                "region": (region or "").strip(),
                "city": "",
                "club": normalize_club_choice(club_choice),
                "flag_path": flag_path,
                "deleted": False,
            })

            save_db(db)
            st.success(f"Добавлен: {name} → {division_id}")
            st.rerun()

st.divider()

participants = [p for p in db.get("participants", []) if not p.get("deleted", False)]

st.session_state.setdefault("pending_delete_id", None)
st.session_state.setdefault("edit_participant_id", None)

edit_id = st.session_state.edit_participant_id
if edit_id is not None:
    target = next((x for x in participants if int(x["id"]) == int(edit_id)), None)
    if target:
        st.subheader(f"Редактировать участника #{edit_id}")
        st.info(f"Сейчас редактируется: {target.get('full_name', '')}")
        with st.form(f"edit_participant_{edit_id}"):
            c1, c2, c3 = st.columns(3)
            with c1:
                edit_name = st.text_input("Фамилия Имя", value=target.get("full_name", ""))
                edit_sex = st.selectbox("Пол", ["M", "F"], index=["M", "F"].index(target.get("sex", "M")), format_func=lambda x: "МУЖЧИНЫ" if x == "M" else "ЖЕНЩИНЫ")
                edit_birth_date = st.date_input(
                    "Дата рождения",
                    format="DD.MM.YYYY",
                    value=parse_birth_date(target.get("birth_date")) or date(2000, 1, 1),
                    min_value=date(1950, 1, 1),
                    max_value=date.today(),
                    key=f"edit_birth_date_{edit_id}",
                )
            with c2:
                edit_category = st.selectbox("Категория", ["BEGSCAL", "INT"], index=["BEGSCAL", "INT"].index(target.get("category", "BEGSCAL")))
                edit_region = st.text_input("Регион", value=target.get("region", "") or target.get("city", ""))
            with c3:
                club_options = club_select_options()
                current_club = target.get("club", "") or "—"
                if current_club not in club_options:
                    club_options = club_options + [current_club]
                edit_club = st.selectbox("Клуб", club_options, index=club_options.index(current_club))
                edit_flag_file = st.file_uploader(
                    "Новый флаг (необязательно)",
                    type=["png", "jpg", "jpeg"],
                    key=f"edit_flag_{edit_id}",
                )

            s1, s2 = st.columns(2)
            save_pressed = s1.form_submit_button("💾 Сохранить")
            cancel_pressed = s2.form_submit_button("Отмена")

        if cancel_pressed:
            st.session_state.edit_participant_id = None
            st.rerun()

        if save_pressed:
            new_division_id = resolve_division_id(edit_sex, edit_category)
            old_division_id = str(target.get("division_id") or "")
            if new_division_id != old_division_id:
                limit = int(db["settings"]["division_limits"].get(new_division_id, 0))
                current = count_participants_in_division(db, new_division_id)
                if limit > 0 and current >= limit:
                    st.error(f"Лимит для {new_division_id} = {limit}. Сейчас уже {current}. Перенос запрещён.")
                    st.stop()

            if not birth_date_to_storage(edit_birth_date):
                st.error("Укажи дату рождения.")
                st.stop()

            target["full_name"] = (edit_name or "").strip()
            target["sex"] = edit_sex
            target["birth_date"] = birth_date_to_storage(edit_birth_date)
            target["age"] = 0
            target["category"] = edit_category
            target["division_id"] = new_division_id
            target["region"] = (edit_region or "").strip()
            target["city"] = ""
            target["club"] = normalize_club_choice(edit_club)
            if edit_flag_file is not None:
                try:
                    target["flag_path"] = save_flag_image(edit_flag_file, int(target["id"]))
                except ValueError as exc:
                    st.error(str(exc))
                    st.stop()

            save_db(db)
            st.session_state.edit_participant_id = None
            st.success("Участник обновлён.")
            st.rerun()

        st.divider()

st.subheader("Список участников")
if not participants:
    st.info("Пока участников нет.")
else:
    sort_labels = {
        "id": "ID",
        "full_name": "ФИО",
        "birth_date": "Дата рождения",
        "age": "Возраст",
        "sex": "Пол",
        "category": "Категория",
        "division_id": "DIV",
        "region": "Регион",
        "club": "Клуб",
    }
    c1, c2, c3 = st.columns([1.4, 1.0, 1.0])
    with c1:
        sort_key = st.selectbox("Сортировка", options=list(sort_labels.keys()), format_func=lambda x: sort_labels[x])
    with c2:
        sort_dir = st.selectbox("Порядок", ["По возрастанию", "По убыванию"])
    with c3:
        st.caption("Список ниже сортируется общим списком, без деления на группы.")

    participants.sort(
        key=lambda p: (
            sort_value(p, sort_key),
            str(p.get("full_name") or "").lower(),
            int(p.get("id") or 0),
        ),
        reverse=(sort_dir == "По убыванию"),
    )

    header = st.columns([0.6, 0.7, 2.3, 0.7, 1.2, 0.8, 1.4, 1.2, 0.8, 0.8])
    labels = ["ID", "Edit", "ФИО", "Пол", "Дата рожд.", "DIV", "Регион", "Клуб", "Флаг", "Del"]
    for col, label in zip(header, labels):
        col.markdown(f"**{label}**")

    for p in participants:
        cols = st.columns([0.6, 0.7, 2.3, 0.7, 1.2, 0.8, 1.4, 1.2, 0.8, 0.8])
        cols[0].write(p["id"])
        if cols[1].button("✏️", key=f"edit_{p['id']}"):
            st.session_state.edit_participant_id = int(p["id"])
            st.rerun()
        cols[2].write(p.get("full_name", ""))
        cols[3].write("МУЖЧИНЫ" if p.get("sex", "") == "M" else "ЖЕНЩИНЫ")
        cols[4].write(display_birth_date(p.get("birth_date")) or "—")
        cols[5].write(p.get("division_id", ""))
        cols[6].write(p.get("region", "") or p.get("city", ""))
        cols[7].write(p.get("club", "") or "—")

        fp = p.get("flag_path")
        if fp:
            try:
                cols[8].image(fp, width=34)
            except Exception:
                cols[8].write("⚠️")
        else:
            cols[8].write("—")

        if cols[9].button("❌", key=f"del_{p['id']}"):
            st.session_state.pending_delete_id = int(p["id"])

if st.session_state.pending_delete_id is not None:
    pid = st.session_state.pending_delete_id
    target = next((x for x in participants if int(x["id"]) == int(pid)), None)
    if target:
        st.warning(f"Удалить участника: **{target['full_name']}** (ID {pid})?")
        c1, c2 = st.columns(2)
        if c1.button("✅ Да, удалить"):
            delete_participant(db, pid)
            save_db(db)
            st.session_state.pending_delete_id = None
            if st.session_state.edit_participant_id == pid:
                st.session_state.edit_participant_id = None
            st.success("Удалено.")
            st.rerun()
        if c2.button("❌ Нет, отмена"):
            st.session_state.pending_delete_id = None
            st.info("Отменено.")
