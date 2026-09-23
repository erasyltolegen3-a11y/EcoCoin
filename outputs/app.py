"""Streamlit interface for the EcoCOin AI Eco-Auditor MVP."""

import hashlib
import os
import streamlit as st

from db import get_balance, init_db
from eco_auditor import audit_cleanup
from main import process_eco_task


st.set_page_config(page_title="EcoCOin — AI Eco-Auditor", page_icon="🌱", layout="wide")
init_db()

st.title("🌱 EcoCOin — AI Eco-Auditor")
st.caption(
    "Загрузите фото уборки общественной территории до и после. Vision-модель "
    "сравнит их, вынесет вердикт и рассчитает награду."
)
st.info(
    "Для MVP проверяется именно уборка мусора на открытой общественной территории. "
    "Изображения будут отправлены в OpenAI API. Сравнение двух фото само по себе "
    "не доказывает, что они сделаны пользователем в реальном времени."
)

user_id = st.number_input("ID пользователя", min_value=1, value=999, step=1)
st.metric("Текущий баланс", f"{get_balance(int(user_id))} EcoCoin")

left, right = st.columns(2)
with left:
    before_photo = st.file_uploader(
        "Фото ДО уборки", type=["png", "jpg", "jpeg", "webp"], key="before_photo"
    )
with right:
    after_photo = st.file_uploader(
        "Фото ПОСЛЕ уборки", type=["png", "jpg", "jpeg", "webp"], key="after_photo"
    )

if before_photo is not None:
    with left:
        st.image(before_photo, caption="До уборки", width="stretch")
if after_photo is not None:
    with right:
        st.image(after_photo, caption="После уборки", width="stretch")

if not os.getenv("OPENAI_API_KEY"):
    st.warning("Перед проверкой задайте переменную среды OPENAI_API_KEY и перезапустите Streamlit.")

if st.button("Проверить фото и обработать отчёт", type="primary"):
    if before_photo is None or after_photo is None:
        st.error("Загрузите оба фото: до и после уборки.")
    else:
        try:
            with st.spinner("AI-аудитор сравнивает фотографии…"):
                ai_response = audit_cleanup(
                    before_bytes=before_photo.getvalue(),
                    before_mime=before_photo.type,
                    after_bytes=after_photo.getvalue(),
                    after_mime=after_photo.type,
                )
                submission_id = hashlib.sha256(
                    before_photo.getvalue() + b"\0" + after_photo.getvalue()
                ).hexdigest()
                result = process_eco_task(
                    int(user_id), ai_response, submission_id=submission_id
                )

            details = ai_response["audit_details"]
            if result.get("already_processed"):
                st.warning(result["message"])
                st.metric(
                    "Баланс без повторного начисления",
                    f"{result['current_balance']} EcoCoin",
                )
            elif result["success"]:
                st.success(result["message"])
                st.metric("Начислено", f"{ai_response['coins_awarded']} EcoCoin")
                st.metric("Новый баланс", f"{result['new_balance']} EcoCoin")
            else:
                st.error(result["message"])
                st.metric("Баланс без изменений", f"{result['current_balance']} EcoCoin")

            with st.expander("Что проверил AI-аудитор"):
                st.write(f"Одна и та же локация: {'да' if details['same_scene'] else 'нет'}")
                st.write(f"Мусор виден до уборки: {'да' if details['litter_before'] else 'нет'}")
                st.write(f"После стало чище: {'да' if details['cleaner_after'] else 'нет'}")
                st.write(f"Собранные мешки видны: {'да' if details['bags_after'] else 'нет'}")
                st.write(f"Оценка объёма работ: {details['work_level']}")
        except Exception as exc:
            st.error(f"Не удалось проверить отчёт: {exc}")
