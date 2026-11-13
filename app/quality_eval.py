#!/usr/bin/env python3
"""10 однакових промптів для обох версій, зберігає реальні відповіді локальної моделі."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

HERE = Path(__file__).resolve().parent
from server import SYSTEM

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument(
        "--label",
        choices=["before", "after", "promptfix", "model4b"],
        required=True
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:11434/v1")
    args = parser.parse_args()
    prompts = json.loads((HERE / "quality_prompts.json").read_text(encoding="utf-8"))
    results = []
    for entry in prompts:
        body = {"model": args.model, "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": entry["prompt"]}],
            "stream": False, "temperature": 0, "max_tokens": 700,
            "reasoning_effort": "none", "seed": 1}
        req = Request(args.base_url.rstrip('/')+"/chat/completions", data=json.dumps(body).encode(),
                      headers={"Content-Type":"application/json"}, method="POST")
        try:
            with urlopen(req, timeout=210) as r:
                response = json.load(r)
            answer = response["choices"][0]["message"].get("content", "")
            if not answer: raise RuntimeError("Порожня відповідь моделі")
            print(f"{entry['id']:02} {entry['topic']}: {answer[:90].replace(chr(10),' ')}")
            error = None
        except (URLError, HTTPError, TimeoutError, KeyError, ValueError, RuntimeError) as exc:
            answer = None
            error = str(exc)
            print(f"{entry['id']:02} ПОМИЛКА: {error}")
        results.append({**entry,"answer":answer,"error":error,"correct":None,
                        "remarks":"Переглянути вручну, чи відповідь відповідає критеріям expected"})
    document = {"model": args.model, "label": args.label,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(), "results":results}
    target = HERE.parent / "demo" / ("quality_"+args.label+".json")
    target.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Збережено",target)
if __name__ == "__main__": main()
