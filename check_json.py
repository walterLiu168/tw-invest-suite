import json
d = json.load(open(r"outputs\margin_rebound\2026-08-17.json", encoding="utf-8"))
print(f"date: {d['date']}")
print(f"threshold: {d['threshold']}")
print(f"count: {d['count']}")
print()
print("first candidate:")
c = d["candidates"][0]
for k, v in c.items():
    print(f"  {k}: {v}")
