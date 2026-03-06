# Agbis Services Dashboard (Streamlit)

Внутренний дашборд для анализа услуг по исполнителям/точкам/периодам из базы Firebird (.fdb) Agbis.

## Быстрый старт (Windows)

1) Установи Python 3.11+ (желательно).
2) Открой PowerShell в папке проекта и создай venv:
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1

3) Установи зависимости:
   pip install -r requirements.txt

4) Создай файл .env рядом с app.py (или скопируй .env.example):
   DB_PATH=C:\Agbis\DB\ARM_13.fdb
   DB_USER=SYSDBA
   DB_PASSWORD=masterkey
   DB_HOST=localhost
   DB_PORT=3050
   DB_CHARSET=UTF8

   > ВАЖНО: Укажи реальные логин/пароль Firebird, которые используются в вашем Agbis.

5) Запусти:
   streamlit run app.py

Откроется браузер с дашбордом.

## Примечания
- По умолчанию запрос ограничен датой DOC_DATE > '2024-01-01' и фильтруется по work_place_id и folder_id (как в вашем ТЗ).
- Данные берутся одним запросом и дальше фильтруются в UI (быстро), есть кэширование.
- Если в базе много данных и нужно ускорить — можно добавить фильтр по периоду прямо в SQL (параметризовано в коде).

## Поля
- DATE_BEG — дата (user_session_actions.date_beg)
- DESCRIPTION — исполнитель (users.description)
- DOC_NUM — заказ (docs.doc_num)
- CODE — код услуги (tovars_tbl.code)
- NAME — название услуги (tovars_tbl.name)
