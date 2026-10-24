"""Search all evidence files for a set of identifiers. Helper for understanding C6."""
import csv, json, sqlite3, sys, re
from pathlib import Path

ROOT = Path("dataset")
EV_FILES = ROOT / "evidence_files.csv"

def load_manifest():
    rows = []
    with open(EV_FILES, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    return rows

def search_sql(path, file_id, needles):
    found = []
    try:
        con = sqlite3.connect(":memory:")
        con.executescript(open(path, encoding="utf-8").read())
    except Exception as e:
        print(f"  {file_id}: SQL load error {e}")
        return found
    tables = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
    for t in tables:
        cols = [c[1] for c in con.execute(f"pragma table_info({t})")]
        for c in cols:
            for n in needles:
                try:
                    rows = con.execute(f"select * from {t} where {c} like ?", (f"%{n}%",)).fetchall()
                    for r in rows:
                        rid = r[0] if r else None
                        found.append((file_id, t, c, n, rid, r))
                except Exception:
                    pass
    return found

def search_json(path, file_id, needles):
    found = []
    try:
        data = json.load(open(path, encoding="utf-8"))
    except Exception as e:
        print(f"  {file_id}: JSON load error {e}")
        return found
    def walk(obj, pathstr=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                walk(v, f"{pathstr}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                walk(v, f"{pathstr}[{i}]")
        elif isinstance(obj, str):
            for n in needles:
                if n in obj:
                    found.append((file_id, pathstr, n, obj[:120]))
    walk(data)
    return found

def search_text(path, file_id, needles):
    found = []
    try:
        txt = open(path, encoding="utf-8", errors="replace").read()
    except Exception as e:
        print(f"  {file_id}: text error {e}")
        return found
    for line in txt.splitlines():
        for n in needles:
            if n in line:
                found.append((file_id, n, line[:160]))
    return found

def main():
    needles = sys.argv[1:]
    if not needles:
        print("usage: py search_evidence.py <needle> [<needle> ...]")
        return
    manifest = load_manifest()
    for m in manifest:
        fid = m["file_id"]
        fpath = ROOT / m["file_path"]
        ext = fpath.suffix.lower()
        if ext == ".sql":
            for hit in search_sql(fpath, fid, needles):
                print("SQL", hit[0], hit[1], hit[2], "needle=", hit[3], "rid=", hit[4], "|", hit[5])
        elif ext == ".json":
            for hit in search_json(fpath, fid, needles):
                print("JSON", hit[0], hit[1], "needle=", hit[2], "|", hit[3])
        elif ext in (".log", ".txt"):
            for hit in search_text(fpath, fid, needles):
                print("TEXT", hit[0], "needle=", hit[1], "|", hit[2])
        else:
            print(f"  {fid}: skipped ext {ext}")

if __name__ == "__main__":
    main()
