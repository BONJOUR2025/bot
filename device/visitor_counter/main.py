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
print("WiFi OK:", wifi.ifconfig()[0])

# D7=GPIO13 — датчик входа, D1=GPIO5 — датчик выхода.
# PULL_UP — иначе пин может висеть в воздухе (floating) и не фиксировать
# переход 1->0, из-за чего срабатывания в одну из сторон не регистрируются.
sensor_in = machine.Pin(13, machine.Pin.IN, machine.Pin.PULL_UP)
sensor_out = machine.Pin(5, machine.Pin.IN, machine.Pin.PULL_UP)

prev_in = sensor_in.value()
prev_out = sensor_out.value()


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
        print("Отправлено:", direction)
    except Exception as e:
        print("Ошибка:", e)


print("Старт")
last_debug = time.ticks_ms()

while True:
    d_in = sensor_in.value()
    d_out = sensor_out.value()

    # Вошёл — sensor_in сработал первым
    if prev_in == 1 and d_in == 0:
        time.sleep_ms(50)
        if sensor_out.value() != 0:
            print(">>> Вошёл")
            send_event("in")

    # Вышел — sensor_out сработал первым
    if prev_out == 1 and d_out == 0:
        time.sleep_ms(50)
        if sensor_in.value() != 0:
            print(">>> Вышел")
            send_event("out")

    prev_in = d_in
    prev_out = d_out

    if time.ticks_diff(time.ticks_ms(), last_debug) > 1000:
        print("in=", d_in, "out=", d_out)
        last_debug = time.ticks_ms()

    time.sleep_ms(50)
