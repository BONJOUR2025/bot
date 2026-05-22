"""
Тест Avito Jobs API: проверяем доступность webhook-эндпоинтов.
Запуск: python test_avito_webhook.py
"""
import urllib.request
import urllib.parse
import urllib.error
import json

CLIENT_ID     = input("Avito Client ID: ").strip()
CLIENT_SECRET = input("Avito Client Secret: ").strip()
CALLBACK_URL  = input("URL для webhook (например http://yourserver.com/api/avito/webhook): ").strip()

BASE = "https://api.avito.ru"

# 1. Получить токен
print("\n[1] Получаем токен...")
data = urllib.parse.urlencode({
    "grant_type": "client_credentials",
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
}).encode()
req = urllib.request.Request(f"{BASE}/token", data=data, method="POST")
req.add_header("Content-Type", "application/x-www-form-urlencoded")
try:
    with urllib.request.urlopen(req) as r:
        token_data = json.loads(r.read())
    access_token = token_data.get("access_token", "")
    print(f"    OK, token: {access_token[:20]}...")
except urllib.error.HTTPError as e:
    print(f"    ОШИБКА {e.code}: {e.read().decode()}")
    exit(1)

headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

def call(method, path, body=None):
    url = BASE + path
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req) as r:
            return r.getcode(), json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()

# 2. Получить список подписок
print("\n[2] GET /job/v1/applications/webhooks (список подписок)...")
code, body = call("GET", "/job/v1/applications/webhooks")
print(f"    {code}: {body}")

# 3. Попробовать зарегистрировать webhook
if CALLBACK_URL:
    print(f"\n[3] PUT /job/v1/applications/webhook (регистрация на {CALLBACK_URL})...")
    code, body = call("PUT", "/job/v1/applications/webhook", {"url": CALLBACK_URL})
    print(f"    {code}: {body}")

# 4. Проверить get_ids
print("\n[4] GET /job/v1/applications/get_ids (проверка доступа к откликам)...")
code, body = call("GET", "/job/v1/applications/get_ids?createdAtFrom=2026-01-01")
print(f"    {code}: {body}")

print("\nГотово.")
