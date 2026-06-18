"""ESP8266 + MicroPython: считает входы/выходы по двум ИК-датчикам разрыва луча
и шлёт события на локальный relay.py (см. README.md в этой папке)."""

import socket
import network
import time
import machine

WIFI_SSID = "<your_wifi_ssid>"
WIFI_PASSWORD = "<your_wifi_password>"

RELAY_HOST = "<relay_pc_ip>"
RELAY_PORT = 8080
RELAY_TIMEOUT_S = 3

wifi = network.WLAN(network.STA_IF)
wifi.active(True)
wifi.connect(WIFI_SSID, WIFI_PASSWORD)
while not wifi.isconnected():
    time.sleep(0.5)
print("WiFi OK")

# PULL_UP — иначе пин может висеть в воздухе (floating) и не фиксировать
# переход 1->0, из-за чего срабатывания в одну из сторон не регистрируются.
sensor1 = machine.Pin(13, machine.Pin.IN, machine.Pin.PULL_UP)
sensor2 = machine.Pin(5, machine.Pin.IN, machine.Pin.PULL_UP)

prev1 = sensor1.value()
prev2 = sensor2.value()


def send_event(direction):
    try:
        s = socket.socket()
        s.settimeout(RELAY_TIMEOUT_S)
        s.connect((RELAY_HOST, RELAY_PORT))
        req = (
            "GET /event?direction=" + direction + " HTTP/1.1\r\n"
            "Host: " + RELAY_HOST + "\r\n"
            "Connection: close\r\n\r\n"
        )
        s.send(req.encode())
        s.recv(512)
        s.close()
    except Exception as e:
        print("Ошибка отправки на relay:", e)


print("Старт")

last_debug = time.ticks_ms()

while True:
    d1 = sensor1.value()
    d2 = sensor2.value()

    if prev1 == 1 and d1 == 0:
        time.sleep_ms(50)
        if sensor2.value() != 0:
            print("Вошёл")
            send_event("in")

    if prev2 == 1 and d2 == 0:
        time.sleep_ms(50)
        if sensor1.value() != 0:
            print("Вышел")
            send_event("out")

    prev1 = d1
    prev2 = d2

    # Раз в секунду печатаем сырые значения датчиков — если sensor2 здесь
    # никогда не показывает 0 при проходе человека, значит проблема в
    # датчике/проводке, а не в логике направления.
    if time.ticks_diff(time.ticks_ms(), last_debug) > 1000:
        print("sensor1=", d1, "sensor2=", d2)
        last_debug = time.ticks_ms()

    time.sleep_ms(50)
