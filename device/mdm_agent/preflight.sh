#!/usr/bin/env bash
# Проверка телефона перед взятием под управление БЕЗ заводского сброса.
#
# Зачем. Стать владельцем устройства на уже работающем телефоне можно, но
# Android ставит жёсткие условия, и главное из них — на аппарате не должно
# остаться НИ ОДНОГО аккаунта. «Вышли из Google» обычно недостаточно: свои
# аккаунты заводят фирменное облако (realme/Heytap, Mi, Samsung), WhatsApp и
# часть других приложений, и в настройках они не всегда лежат на виду.
#
# Скрипт только СМОТРИТ и ничего не меняет: его можно запускать сколько угодно
# раз, в том числе чтобы убедиться, что после чистки аккаунтов стало можно.
#
# Запуск (из Git Bash):
#   bash /c/deploy/bot-repo/device/mdm_agent/preflight.sh
set -u

ADB="${ADB:-/c/deploy/platform-tools/adb.exe}"
PKG="pw.bonjour.mdm"
ADMIN="$PKG/$PKG.AdminReceiver"

if [ ! -x "$ADB" ] && ! command -v "$ADB" >/dev/null 2>&1; then
  echo "adb не найден: $ADB"
  echo "Укажите путь: ADB=/путь/к/adb.exe bash $0"
  exit 1
fi

count_devices() { "$ADB" devices | sed -n '2,$p' | grep -c "device$"; }

echo "=== Телефон ==="
n=$(count_devices)
if [ "$n" -eq 0 ]; then
  echo "  НЕ ГОТОВО: телефон не виден по adb."
  echo "  Включите «Отладка по USB» в параметрах разработчика и разрешите"
  echo "  подключение с этого компьютера (запрос появится на экране телефона)."
  exit 1
fi
if [ "$n" -gt 1 ]; then
  echo "  НЕ ГОТОВО: подключено несколько устройств — оставьте одно."
  exit 1
fi

model=$("$ADB" shell getprop ro.product.model 2>/dev/null | tr -d '\r')
android=$("$ADB" shell getprop ro.build.version.release 2>/dev/null | tr -d '\r')
echo "  $model, Android $android"

ready=0

echo
echo "=== Аккаунты (главное препятствие) ==="
accounts=$("$ADB" shell dumpsys account 2>/dev/null | tr -d '\r' | grep -o 'Account {name=[^}]*}' | sed 's/Account {name=//; s/}$//')
if [ -z "$accounts" ]; then
  echo "  ок: аккаунтов нет"
else
  ready=1
  echo "  НЕ ГОТОВО: на телефоне остались аккаунты —"
  echo "$accounts" | sed 's/^/    · /'
  echo "  Удалите их все: Настройки → Аккаунты. Фирменное облако телефона и"
  echo "  часть приложений заводят свои аккаунты, их тоже нужно убрать."
fi

echo
echo "=== Управление ==="
owners=$("$ADB" shell dpm list-owners 2>/dev/null | tr -d '\r')
case "$owners" in
  *"$PKG"*)
      echo "  уже наш агент — телефон под управлением, делать нечего"; ready=2 ;;
  *"Device owner"*|*"Profile owner"*)
      ready=1
      echo "  НЕ ГОТОВО: на телефоне уже есть владелец/владелец профиля:"
      echo "$owners" | sed 's/^/    /'
      echo "  Такой аппарат берётся только через заводской сброс." ;;
  *)  echo "  ок: владельца устройства нет" ;;
esac

admins=$("$ADB" shell dpm list-admins 2>/dev/null | tr -d '\r' | grep -v '^$' | grep -vi 'admin receivers')
if [ -n "$admins" ]; then
  echo "  внимание: есть активные администраторы устройства —"
  echo "$admins" | sed 's/^/    /'
  echo "  Их надо отключить: Настройки → Безопасность → Приложения-администраторы."
fi

echo
echo "=== Пользователи ==="
users=$("$ADB" shell pm list users 2>/dev/null | tr -d '\r' | grep -c 'UserInfo{')
if [ "$users" -le 1 ]; then
  echo "  ок: один пользователь"
else
  ready=1
  echo "  НЕ ГОТОВО: пользователей на телефоне $users — удалите лишних и гостя."
fi

echo
echo "=== Итог ==="
if [ "$ready" -eq 2 ]; then
  echo "  Телефон уже под нашим управлением."
  exit 0
fi
if [ "$ready" -eq 0 ]; then
  cat <<EOF
  ГОТОВ. Данные телефона при этом НЕ стираются — приложения, фотографии и
  настройки остаются на месте, уходят только аккаунты (их можно вернуть сразу
  после). Команды:

    "$ADB" install -r путь/к/app-release.apk
    "$ADB" shell dpm set-device-owner $ADMIN

  Дальше на телефоне открыть «BONJOUR MDM», вписать адрес сервера и ключ
  регистрации, нажать «Зарегистрировать телефон».

  Если вторая команда откажет — она ничего не ломает и не стирает: телефон
  останется как был, а в тексте ошибки будет причина.
EOF
else
  echo "  НЕ ГОТОВ — см. пункты выше. Пока они не устранены, брать телефон"
  echo "  под управление без заводского сброса не получится."
fi
