import sqlite3
from pathlib import Path

def init_db(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as con:
        con.execute("""
        create table if not exists plans (
            month text not null,
            emp_code text not null,
            plan_repair real not null default 0,
            plan_cosm real  not null default 0,
            plan_shoes real not null default 0,
            primary key (month, emp_code)
        )
        """)
        con.commit()

def get_plans(db_path: Path, month: str) -> dict[str, dict]:
    with sqlite3.connect(db_path) as con:
        cur = con.execute("select emp_code, plan_repair, plan_cosm, plan_shoes from plans where month=?", (month,))
        out = {}
        for code, pr, pc, ps in cur.fetchall():
            out[code] = {"repair": float(pr or 0), "cosm": float(pc or 0), "shoes": float(ps or 0)}
        return out

def upsert_plan(db_path: Path, month: str, emp_code: str, repair: float, cosm: float, shoes: float):
    with sqlite3.connect(db_path) as con:
        con.execute("""
        insert into plans(month, emp_code, plan_repair, plan_cosm, plan_shoes)
        values(?,?,?,?,?)
        on conflict(month, emp_code) do update set
            plan_repair=excluded.plan_repair,
            plan_cosm=excluded.plan_cosm,
            plan_shoes=excluded.plan_shoes
        """, (month, emp_code, float(repair or 0), float(cosm or 0), float(shoes or 0)))
        con.commit()
