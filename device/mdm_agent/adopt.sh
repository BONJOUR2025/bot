#!/usr/bin/env bash
# Взятие телефона под управление одной командой.
#
# Пара к preflight.sh: тот только смотрит, этот — делает. Порядок и проверки
# вынесены сюда, чтобы не вспоминать их на каждом аппарате и не повторять
# ошибок, которые уже стоили нам полутора часов на первом Redmi.
#
# Запуск (из Git Bash):
#   bash /c/deploy/bot-repo/device/mdm_agent/adopt.sh [путь/к/agent.apk]
#
# Без аргумента APK скачивается с сервера.
set -u

ADB="${ADB:-/c/deploy/platform-tools/adb.exe}"
PKG="pw.bonjour.mdm"
ADMIN="$PKG/$PKG.AdminReceiver"
APK_URL="${APK_URL:-https://app.bonjour.pw/api/mdm/agent.apk}"
APK="${1:-}"

say() { echo; echo "=== $* ==="; }
die() { echo; echo "ОСТАНОВЛЕНО: $*"; exit 1; }

adb_() { MSYS_NO_PATHCONV=1 "$ADB" "$@"; }

# --- телефон ---------------------------------------------------------------
say "Телефон"
n=$(adb_ devices | sed -n '2,$p' | grep -c "device$")
[ "$n" -eq 1 ] || die "нужен ровно один телефон по adb (сейчас $n). Включите «Отладка по USB»."
echo "  $(adb_ shell getprop ro.product.brand 2>/dev/null | tr -d '\r') \
$(adb_ shell getprop ro.product.model 2>/dev/null | tr -d '\r'), \
Android $(adb_ shell getprop ro.build.version.release 2>/dev/null | tr -d '\r')"

# --- аккаунты --------------------------------------------------------------
# Проверяем до всего остального: set-device-owner сначала назначает приложение
# администратором и только потом владельцем. С аккаунтами вторая половина
# падает, а первая остаётся — телефон с активным администратором, которого
# снимать руками.
say "Аккаунты"
accounts=$(adb_ shell dumpsys account 2>/dev/null | tr -d '\r' \
  | grep -E '^[[:space:]]*Account \{' | grep -o 'type=[^}]*' | sort -u)
if [ -n "$accounts" ]; then
  echo "$accounts" | sed 's/^/  · /'
  echo
  echo "  Удалите все. Записи приложений (WhatsApp, VK) убираются удалением или"
  echo "  очисткой самого приложения, и после этого НУЖНА ПЕРЕЗАГРУЗКА: строка"
  echo "  удалённого приложения висит в системной базе до неё и блокирует."
  die "на телефоне есть аккаунты"
fi
echo "  ок: пусто"

# --- установка агента ------------------------------------------------------
say "Агент"
installed=$(adb_ shell dumpsys package "$PKG" 2>/dev/null | tr -d '\r' | grep -m1 versionName | sed 's/.*versionName=//')
if [ -n "$installed" ]; then
  echo "  уже установлен: $installed"
else
  if [ -z "$APK" ]; then
    APK=$(mktemp -t agent.XXXXXX).apk
    echo "  качаю $APK_URL"
    curl -fsS -o "$APK" "$APK_URL" || die "не скачался APK"
  fi
  if adb_ install -r "$APK" 2>&1 | grep -q Success; then
    echo "  установлен через adb"
  else
    # Прошивки Xiaomi запрещают установку через adb (INSTALL_FAILED_USER_RESTRICTED).
    # Установка, начатая на самом телефоне, под этот запрет не подпадает.
    adb_ push "$APK" /sdcard/Download/bonjour-mdm.apk >/dev/null 2>&1
    echo "  adb ставить не дали (обычное дело на Xiaomi)."
    die "откройте на телефоне Проводник → Загрузки → bonjour-mdm.apk, установите и запустите скрипт снова"
  fi
fi

# --- владелец устройства ---------------------------------------------------
say "Владелец устройства"
owners=$(adb_ shell dpm list-owners 2>/dev/null | tr -d '\r')
if echo "$owners" | grep -q "$PKG"; then
  echo "  уже наш агент"
else
  out=$(adb_ shell dpm set-device-owner "$ADMIN" 2>&1 | tr -d '\r')
  if echo "$out" | grep -q "Success"; then
    echo "  назначен"
  else
    echo "$out" | head -3 | sed 's/^/  /'
    case "$out" in
      *"not authorized"*)
        echo
        echo "  Это замок прошивки Xiaomi. Нужны в «Для разработчиков»:"
        echo "    · «Отладка по USB (настройки безопасности)» — требует входа в Mi-аккаунт"
        echo "      (после включения из аккаунта можно выйти);"
        echo "    · режим USB именно «Передача файлов» (mtp), не только зарядка —"
        echo "      без него переключатель включён, а прав нет."
        echo "    Сейчас режим: $(adb_ shell getprop sys.usb.config 2>/dev/null | tr -d '\r')"
        ;;
      *accounts*) echo "  Остались аккаунты — см. выше про перезагрузку." ;;
    esac
    die "владельцем стать не удалось"
  fi
fi

# --- Play Защита -----------------------------------------------------------
# По воздуху не выключается: проверено на Android 16 — Android отказывает
# владельцу устройства во всех трёх ключах. Поэтому делаем здесь, пока кабель
# подключён: иначе тихая установка приложений на этот телефон не поедет.
say "Play Защита"
for kv in "package_verifier_user_consent -1" "package_verifier_enable 0" "verifier_verify_adb_installs 0"; do
  set -- $kv
  adb_ shell settings put global "$1" "$2" >/dev/null 2>&1
done
consent=$(adb_ shell settings get global package_verifier_user_consent 2>/dev/null | tr -d '\r')
if [ "$consent" = "-1" ]; then
  echo "  выключена (тихая установка приложений будет работать)"
else
  echo "  НЕ ВЫКЛЮЧИЛАСЬ (package_verifier_user_consent=$consent)."
  echo "  Выключите руками: Play Маркет → профиль → Play Защита → шестерёнка."
fi

# --- сканер MIUI -----------------------------------------------------------
# Прошивки Xiaomi гоняют свой антивирус на каждой установке. По логам Redmi
# 2409BRN2CY: сама проверка занимает полсекунды, но MIUI держит её минимум
# шесть секунд (CheckVirusTaskV2 «min: 6000») и норовит показать в окне рекламу.
# На установке приложения из библиотеки это стоило 11 секунд из 37.
#
# Через adb его не погасить: `pm disable-user` отвечает «Cannot disable system
# packages» даже с открытыми настройками безопасности. Гасится только правами
# владельца устройства, то есть нашей же командой из панели — а она доступна
# после регистрации. Поэтому здесь только напоминание.
case "$(adb_ shell getprop ro.product.brand 2>/dev/null | tr -d '' | tr 'A-Z' 'a-z')" in
  xiaomi|redmi|poco)
    say "Сканер MIUI"
    echo "  Прошивка сканирует каждую установку и держит окно 6 секунд."
    echo "  Через adb не отключается (системный пакет). После регистрации"
    echo "  телефона отправьте ему команду скрытия:"
    echo "    set_app_enabled  package=com.miui.guardprovider  enabled=false"
    ;;
esac

# --- итог ------------------------------------------------------------------
say "Готово"
adb_ shell dpm list-owners 2>/dev/null | tr -d '\r' | sed 's/^/  /'
cat <<EOF

  Осталось зарегистрировать агент на сервере: на телефоне открыть
  «BONJOUR MDM», вписать ключ регистрации и нажать «Зарегистрировать телефон».
  Адрес сервера уже подставлен.

  После регистрации телефон появится в панели и начнёт отвечать за секунды.
EOF
