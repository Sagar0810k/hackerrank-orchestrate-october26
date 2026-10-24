"""Dev helper: list tables of a SQL snapshot and rows matching search terms.

Usage: python code/tools/inspect_sql.py <file.sql> [needle ...]
"""
import sqlite3
import sys

path, needles = sys.argv[1], sys.argv[2:]
con = sqlite3.connect(":memory:")
try:
    con.executescript(open(path, encoding="utf-8").read())
except sqlite3.Error as e:
    print("executescript error:", e)
tables = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
for t in tables:
    cols = [r[1] for r in con.execute(f'pragma table_info("{t}")')]
    cnt = con.execute(f'select count(*) from "{t}"').fetchone()[0]
    print(f"{t}: cols={cols} count={cnt}")
    for c in cols:
        for needle in needles:
            rows = con.execute(f'select * from "{t}" where "{c}" like ?', (f"%{needle}%",)).fetchall()
            for row in rows:
                print(f"  MATCH {t}.{c} ~ {needle}: {row}")
