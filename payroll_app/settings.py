from pathlib import Path

# Excel с окладами (лист = название месяца: ЯНВАРЬ, ФЕВРАЛЬ, ...)
EXCEL_FOT = Path(r"C:\Users\hrbon\Desktop\telegram_bot\ФОТ админы 2026.xlsx")

# Firebird база (Agbis)
FDB_PATH  = r"C:\Agbis\DB\ARM_13.fdb"

# Если Firebird требует учётные данные — заполните
FDB_USER = None  # например: "SYSDBA"
FDB_PASS = None  # например: "masterkey"
FDB_HOST = "localhost"  # или IP/hostname
FDB_PORT = 3050

# JSON файлы
ADVANCES_JSON = Path(r"C:\Users\hrbon\Desktop\telegram_bot\advance_requests.json")
BONUSES_JSON  = Path(r"C:\Users\hrbon\Desktop\telegram_bot\bonuses_penalties.json")

# Локальная SQLite для планов
SQLITE_DB = Path(r".\data\config.db")
