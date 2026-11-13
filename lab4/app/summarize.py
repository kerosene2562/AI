import csv, json
from pathlib import Path
root = Path(__file__).resolve().parent.parent
csvpath = root / "bench_results.csv"
if csvpath.exists():
    rows = list(csv.DictReader(csvpath.open(encoding="utf-8")))
    if rows:
        print("Заміри, один користувач:")
        for row in rows:
            if row.get("concurrency")=="1":
                print(f"{row['label']} | {row['model']} | TTFT p50 {row['ttft_p50_s']} c | токенів/с {row['tokens_per_s_per_user_p50']}")
    else: print("Заміри відсутні. Запусти bench.py до і після оптимізації")
for label in ("before", "after"):
    path = root / "demo" / f"quality_{label}.json"
    if not path.exists():
        print(f"{label}: файл якості відсутній")
        continue
    data = json.loads(path.read_text(encoding="utf-8"))
    results = data["results"]
    answered = sum(bool(r.get("answer")) for r in results)
    reviewed = sum(isinstance(r.get("correct"), bool) for r in results)
    correct = sum(r.get("correct") is True for r in results)
    print(f"{label}: отримано {answered}/{len(results)} відповідей; "
          f"оцінено {reviewed}/{len(results)}; правильних {correct}/{reviewed if reviewed else len(results)}")
    if reviewed < len(results):
        print("  Є неперевірені відповіді: заповни correct (true/false) і remarks")
