"""Локальный relay: принимает простые GET-запросы от ESP8266 по локальной сети
и пересылает их на облачный эндпоинт /api/visitor-events/ingest по HTTPS.
ESP8266 не умеет нормально работать с TLS, поэтому HTTPS-запрос делает этот
сервер, запущенный на обычном ПК в той же сети, что и плата."""

from flask import Flask, request
import requests

app = Flask(__name__)

API_KEY = "<api_key_from_admin_ui>"
SALON_CODE = "<salon_code>"
URL = "https://app.bonjour.pw/api/visitor-events/ingest"
REQUEST_TIMEOUT_S = 5


@app.route("/event")
def event():
    direction = request.args.get("direction", "in")
    try:
        r = requests.post(
            URL,
            json={
                "salon_code": SALON_CODE,
                "direction": direction,
                "count": 1,
                "device_id": "esp8266-01",
            },
            headers={"X-API-Key": API_KEY},
            timeout=REQUEST_TIMEOUT_S,
        )
        print(r.status_code, r.text)
        return r.text, r.status_code
    except requests.RequestException as e:
        print("Ошибка отправки в облако:", e)
        return f"relay_error: {e}", 502


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, threaded=True)
