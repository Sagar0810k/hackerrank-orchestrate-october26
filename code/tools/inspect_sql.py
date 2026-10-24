import sqlite3, sys
path = sys.argv[1]
con = sqlite3.connect(":memory:")
sql = open(path, encoding="utf-8").read()
try:
    con.executescript(sql)
except Exception as e:
    print("executescript error:", e)
tables = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
print("TABLES:", tables)
for t in tables:
    cols = [r[1] for r in con.execute(f"pragma table_info({t})")]
    cnt = con.execute(f"select count(*) from {t}").fetchone()[0]
    print(f"  {t}: cols={cols} count={cnt}")
try:
    print("snapshot_scope:", con.execute("select * from snapshot_scope").fetchall())
except Exception as e:
    print("no snapshot_scope:", e)
for t in tables:
    cols = [r[1] for r in con.execute(f"pragma table_info({t})")]
    for c in cols:
        for needle in ("amina.elmasri", "user_01", "mateo.rios", "user_02"):
            try:
                rows = con.execute(f"select * from {t} where {c} like ?", (f"%{needle}%",)).fetchall()
                if rows:
                    print(f"MATCH {t}.{c} ~ {needle}:", rows[:3])
            except Exception:
                pass
    if 'resource_id' in cols:
        rows = con.execute(f"select * from {t}").fetchall()
        print(f"{t} ALL ROWS:")
        for r in rows:
            print("   ", r)
