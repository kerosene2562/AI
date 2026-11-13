#!/usr/bin/env python3
"""Локальний вебсервер для АвтоДіагноста, без зовнішніх Python-бібліотек."""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
OLLAMA = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
PORT = int(os.getenv("APP_PORT", "8000"))
MODEL = os.getenv("AUTO_MODEL", "qwen3:1.7b-q4_K_M")
MODEL_CHOICES = {"qwen3:1.7b-q4_K_M", "qwen3:1.7b-q8_0"}

SYSTEM = """Ти АвтоДіагност, помічник з первинної діагностики несправностей легкових авто.
Відповідай українською, конкретно і зрозуміло для власника авто. Немає доступу до ЕБУ,
реальних датчиків, мультиметра чи сервісної документації. Ніколи не видавай ймовірну
причину за точний діагноз. Якщо даних мало - прямо скажи, які дані потрібні.
Будь обережний із кодами: уточнюй марку і трактування виробника, якщо код не загальний OBD-II.
Не радь самостійно роз'єднувати компоненти SRS, піротехнічні роз'єми, HV-батареї,
відкривати гарячий контур охолодження або працювати під авто без опор.
Для проблем із гальмами, кермом, значним перегрівом, запахом пального, димом чи
критичними попередженнями порадь зупинити авто та звернутися до фахівця.
Структура відповіді (коротко): 1) Що може означати симптом або код,
2) 2-4 можливі причини, 3) що безпечно перевірити спочатку,
4) коли потрібен сервіс і чи можна продовжувати рух.
Не вигадуй посилань на мануали, кодів помилок чи результатів діагностики."""

SYSTEM += """
Довідкові відомості для автомобільної діагностики:

P0301: пропуски запалювання у першому циліндрі.
Можливі перевірки: свічка, котушка, форсунка,
паливна система, компресія.
Якщо Check Engine блимає, безпечно зупинитися.

P0171: надто збіднена паливоповітряна суміш,
банк 1. Перевірити підсмоктування повітря,
MAF і подачу пального.

P0420: ефективність каталізатора нижча за поріг.
Не рекомендувати негайну заміну.
Спочатку перевірити датчики кисню,
витоки вихлопу та роботу двигуна.

P0128: температура охолоджувальної рідини
нижча за очікувану. Перевірити термостат
і датчик температури.

P0562: низька напруга бортової мережі.
Перевірити АКБ, генератор, клеми,
масу та напругу мультиметром.

SRS: якщо горить Airbag, попередити про
можливу несправність системи безпеки.
Не рекомендувати самостійно перевіряти
електричні кола подушок безпеки.

Перегрів із парою: безпечно зупинитися,
не відкривати гарячий бачок охолодження,
звернутися по допомогу.

Педаль гальма провалюється: не продовжувати
рух, рекомендувати евакуатор.

Вентилятор салону не працює: перевірити
запобіжник, живлення, мотор вентилятора
і регулятор швидкості.

Якщо симптоми невизначені, не вигадуй
несправність. Постав уточнювальні питання.

Використовуй довідкові відомості лише для
відповідного випадку. Не вигадуй технічних
термінів і не повторюй беззмістовні фрази.
Якщо інформації недостатньо, прямо скажи про це.
"""

class Handler(BaseHTTPRequestHandler):
    def respond(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/api/health":
            try:
                with urlopen(OLLAMA + "/api/tags", timeout=4) as res:
                    models = json.load(res)
                names = [m.get("name", "") for m in models.get("models", [])]
                self.respond(200, {"ok": True, "models": names, "default_model": MODEL})
            except (OSError, ValueError) as exc:
                self.respond(503, {"ok": False, "error": "Ollama не відповідає: " + str(exc)})
            return
        path = "index.html" if self.path in ("/", "/index.html") else None
        if not path:
            self.respond(404, {"error": "Сторінку не знайдено"})
            return
        data = (HERE / path).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path != "/api/analyze":
            self.respond(404, {"error": "Невідомий маршрут"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length < 16000:
                raise ValueError("Запит завеликий або порожній")
            data = json.loads(self.rfile.read(length))
            model = str(data.get("model") or MODEL)
            if model not in MODEL_CHOICES:
                raise ValueError("Невідома модель")
            fields = [("Автомобіль", "vehicle"), ("Рік", "year"),
                      ("Двигун", "engine"), ("Коди несправностей", "codes"),
                      ("Симптоми", "symptoms"), ("Додаткова інформація", "extra")]
            details = []
            for label, field in fields:
                value = str(data.get(field) or "").strip()[:1500]
                if value:
                    details.append(f"{label}: {value}")
            if not str(data.get("symptoms") or "").strip() and not str(data.get("codes") or "").strip():
                raise ValueError("Укажи симптоми або код помилки")
            body = {
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {
                        "role": "user",
                        "content": "Оціни цей випадок:\n" + "\n".join(details)
                    }
                ],
                "stream": True,
                "temperature": 0,
                "max_tokens": 600,
                "reasoning_effort": "none",
                "seed": 1
            }
            req = Request(OLLAMA + "/v1/chat/completions",
                          data=json.dumps(body).encode("utf-8"),
                          headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(req, timeout=180) as response:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()
                for line in response:
                    self.wfile.write(line)
                    self.wfile.flush()
            self.close_connection = True
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.respond(400, {"error": str(exc)})
        except HTTPError as exc:
            message = exc.read(400).decode("utf-8", errors="replace")
            self.respond(502, {"error": "Помилка Ollama (" + str(exc.code) + "): " + message})
        except (OSError, URLError, TimeoutError) as exc:
            try:
                self.respond(503, {"error": "Сервер моделі недоступний або таймаут: " + str(exc)})
            except (BrokenPipeError, ConnectionResetError):
                pass

if __name__ == "__main__":
    print(f"АвтоДіагност: http://127.0.0.1:{PORT}; модель: {MODEL}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
