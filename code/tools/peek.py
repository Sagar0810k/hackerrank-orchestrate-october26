import csv, sys
path = sys.argv[1]
with open(path, newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))
print("columns:", list(rows[0].keys()) if rows else "EMPTY")
print("row count:", len(rows))
for r in rows[:5]:
    print(r)
