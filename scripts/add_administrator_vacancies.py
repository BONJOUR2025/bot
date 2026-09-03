"""Разовое заведение двух вакансий администратора-продавца и связок с hh.

Вакансии две, а не одна, потому что места работы разные: Охта Молл и Гранд
Палас. Кандидату важно, куда ездить, а нам — не смешивать в одной воронке
людей, которым удобно на разных концах города.

    python scripts/add_administrator_vacancies.py            # только показать
    python scripts/add_administrator_vacancies.py --apply    # завести

Идемпотентен: вакансия с таким названием и связка с таким external_id
второй раз не создаются.
"""
from __future__ import annotations

import argparse
import json
import sys

from app.db.session import SessionLocal, init_db
from app.models.recruitment import RecruitmentSource, Vacancy, VacancyLink

# Текст с hh — тот же, что видит кандидат в объявлении. Расходиться им
# нельзя: бот отвечает на вопросы по нему же.
DESCRIPTION = """Бонжур — это сеть салонов по пошиву, ремонту, реставрации и химчистке обуви и сумок в Петербурге.

Ваш функционал:
— приём и выдача заказов на реставрацию;
— консультирование по услугам реставрации и ремонта;
— контроль сроков выполнения заказа;
— продажа готовой обуви и обувной косметики;
— работа с кассой.

Ваши компетенции и навыки:
— вы не боитесь общения с клиентами;
— грамотная устная и письменная речь;
— знание ПК на уровне пользователя;
— ответственное отношение к работе;
— готовность к обучению (оплачивается).

Мы предлагаем:
— заработную плату {salary}, без задержек, 2 раза в месяц;
— оклад + % от принятых на реставрацию изделий и продаж + премии + KPI;
— оформление по вашему желанию;
— режим работы 2/2, {hours};
— бесплатные тренинги и обучение, скидки на услуги и товары;
— корпоративную форму, чай и угощения за счёт компании, подарки ко дню рождения.

Место работы: {place}, {address}."""

# Что для этой вакансии профильный опыт. Раньше это стояло в общем промпте
# словами «работа руками с кожей» — по такой рубрике администратор-продавец
# получал бы «подходящего опыта нет», кем бы он ни был.
CRITERIA = """Профильный опыт: работа с клиентами лицом к лицу — продавец, администратор,
приёмщик заказов, кассир, официант, бариста, сотрудник салона или пункта выдачи,
любая розница и сфера услуг.
Смежный опыт: работа с людьми не в торговом зале — оператор call-центра, менеджер
по продажам, консультант, ресепшен, а также любая работа с кассой, деньгами и
документами.
Отсутствие опыта именно в обуви и коже недостатком не является: обучение
оплачивается и проводится компанией.
Отдельно отметь в to_ask, если из данных не видно, как далеко кандидату
добираться до салона: в рознице со сменой 2/2 это первая причина ухода."""

VACANCIES = [
    {
        "title": 'Администратор-продавец — ТЦ "Охта Молл"',
        "place": 'ТЦ "Охта Молл"',
        "address": "Санкт-Петербург, Брантовская дорога, 3",
        "salary": "от 60 000 до 80 000 рублей",
        "hours": "с 10:00 до 22:00",
        "external_id": "136019715",
    },
    {
        "title": 'Администратор-продавец — ТД "Гранд Палас"',
        "place": 'ТД "Гранд Палас"',
        "address": "Санкт-Петербург, Невский проспект, 44",
        "salary": "от 50 000 до 80 000 рублей",
        "hours": "с 11:00 до 21:00",
        "external_id": "136019770",
    },
]

# Вопрос про актуальность поиска бот задаёт сам, отдельной фазой перед этими
# (quick_screening.INTEREST_QUESTION) — дублировать его здесь не нужно.
def questions(v: dict) -> list[str]:
    return [
        "Есть ли у вас опыт работы с клиентами — в продажах, на приёме заказов, "
        "в сфере услуг? Расскажите, где и как долго.",
        f"Салон находится по адресу: {v['address']} ({v['place']}). "
        "Вам удобно будет добираться до этого места?",
    ]


DEAL_BREAKERS = [{"label": "Город проживания",
                  "value": "Санкт-Петербург и Ленинградская область"}]

# «О компании» — то же, что у мастерской. «Регламент работы
# администратора-продавца» и «Рабочий день администратора» не подключаем:
# это внутренние инструкции (Таск Менеджер, сверка кассы, рабочие чаты), и
# бот не должен пересказывать их кандидату.
KNOWLEDGE_DOCS = [4]

STRATEGY_ID = 2  # Быстрый найм — та же, что у мастерской

# Собеседование там же, где у мастеров: другого подтверждённого адреса нет.
INTERVIEW_LOCATION = (" Наше производство и центральный офис, ул. Бестужевская, д. 10. "
                      " Вход со стороны пр. Мечникова (рядом с OZON), по лестнице на 2 этаж "
                      "и налево. На ресепшн скажите, что на собеседование. "
                      "От ст. м. Лесная удобнее добираться на автобусе №237")


def run(apply: bool) -> int:
    init_db()
    db = SessionLocal()
    made = 0
    try:
        src = db.query(RecruitmentSource).filter(RecruitmentSource.source == "hh").first()
        if not src:
            print("Источник hh не настроен.")
            return 0

        for v in VACANCIES:
            exists = db.query(Vacancy).filter(Vacancy.title == v["title"]).first()
            qs = questions(v)
            print("=" * 68)
            print(v["title"])
            if exists:
                print(f"  уже заведена (id={exists.id}) — пропускаю")
                continue
            print(f"  адрес     : {v['address']}")
            print(f"  зарплата  : {v['salary']}, смена {v['hours']}")
            print(f"  стратегия : {STRATEGY_ID} (Быстрый найм)")
            print(f"  hh        : {v['external_id']}")
            print("  вопросы бота:")
            print("    0. (встроенный) Подскажите, вы ещё в поиске работы?")
            for i, q in enumerate(qs, 1):
                print(f"    {i}. {q}")
            if not apply:
                continue

            vac = Vacancy(
                title=v["title"],
                description=DESCRIPTION.format(**v),
                is_open=True,
                interview_location=INTERVIEW_LOCATION,
                strategy_id=STRATEGY_ID,
                extra_instructions=CRITERIA,
                deal_breakers_json=json.dumps(DEAL_BREAKERS, ensure_ascii=False),
                custom_questions_json=json.dumps(qs, ensure_ascii=False),
                knowledge_document_ids_json=json.dumps(KNOWLEDGE_DOCS),
                quick_mode_enabled=True,
                quick_questions_json=json.dumps(qs, ensure_ascii=False),
            )
            db.add(vac)
            db.flush()

            link = db.query(VacancyLink).filter(
                VacancyLink.source == "hh",
                VacancyLink.external_vacancy_id == v["external_id"]).first()
            if not link:
                db.add(VacancyLink(
                    vacancy_id=vac.id,
                    source="hh",
                    source_id=src.id,
                    external_vacancy_id=v["external_id"],
                    external_vacancy_title=v["title"],
                    sync_enabled=True,
                ))
            made += 1
            print(f"  заведена: id={vac.id}")

        if apply:
            db.commit()
            print(f"\nсоздано вакансий: {made}")
        else:
            print("\nНичего не изменено — запустите с --apply.")
        return made
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="завести, а не показать")
    args = ap.parse_args()
    sys.exit(0 if run(args.apply) >= 0 else 1)
