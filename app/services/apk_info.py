"""Чтение имени пакета и версии из APK без сторонних библиотек.

Зачем свой разбор: чтобы поставить приложение на телефон, знать имя пакета не
обязательно — установщик Android разберётся сам. Но без него панель не сможет
ни сказать «это приложение уже стоит на трёх телефонах», ни предложить удалить
его одной кнопкой, а оператору пришлось бы вбивать `com.whatsapp` руками.

Разбор устроен как «лучшее усилие»: всё, что не удалось прочитать, возвращается
как None, и вызывающий код спокойно живёт без этих данных. Поэтому здесь нет ни
одного исключения наружу — экзотический APK не должен ломать загрузку файла.

Формат — бинарный AndroidManifest.xml (AXML): заголовок, пул строк, дальше
чанки тегов. Нам нужен первый тег `manifest` и три его атрибута.
"""

from __future__ import annotations

import io
import json
import struct
import zipfile
from typing import Any, Optional

# Типы чанков AXML
_CHUNK_STRING_POOL = 0x0001
_CHUNK_START_TAG = 0x0102

_FLAG_UTF8 = 1 << 8

# Тип значения атрибута: строка из пула / целое
_TYPE_STRING = 0x03
_TYPE_INT_DEC = 0x10


def read_apk_info(content: bytes) -> dict[str, Any]:
    """@return {"package": str|None, "version_name": str|None, "version_code": int|None}"""
    empty = {"package": None, "version_name": None, "version_code": None}
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            manifest = archive.read("AndroidManifest.xml")
    except Exception:
        return empty
    try:
        return _parse_manifest(manifest)
    except Exception:
        return empty


def _parse_manifest(data: bytes) -> dict[str, Any]:
    strings = _read_string_pool(data)
    if not strings:
        return {"package": None, "version_name": None, "version_code": None}

    wanted = {"package": None, "versionName": None, "versionCode": None}

    # Первый чанк файла — заголовок, дальше идут чанки подряд.
    offset = 8
    while offset + 8 <= len(data):
        chunk_type, header_size, chunk_size = _chunk_header(data, offset)
        if chunk_size <= 0 or offset + chunk_size > len(data):
            break
        if chunk_type == _CHUNK_START_TAG:
            name_index = struct.unpack_from("<I", data, offset + 20)[0]
            if _string(strings, name_index) == "manifest":
                _read_attributes(data, offset, header_size, strings, wanted)
                break
        offset += chunk_size

    version_code = wanted["versionCode"]
    return {
        "package": wanted["package"],
        "version_name": wanted["versionName"],
        "version_code": int(version_code) if isinstance(version_code, int) else None,
    }


def _chunk_header(data: bytes, offset: int) -> tuple[int, int, int]:
    chunk_type, header_size = struct.unpack_from("<HH", data, offset)
    (chunk_size,) = struct.unpack_from("<I", data, offset + 4)
    return chunk_type, header_size, chunk_size


def _read_attributes(
    data: bytes, tag_offset: int, header_size: int, strings: list[str], wanted: dict
) -> None:
    # Поля лежат сразу за заголовком чанка: ns(4), name(4), затем три uint16 —
    # смещение атрибутов, их размер и количество. Само смещение отсчитывается
    # от конца заголовка, а не от начала чанка.
    attr_start, attr_size, attr_count = struct.unpack_from("<HHH", data, tag_offset + 24)
    base = tag_offset + header_size + attr_start
    for i in range(attr_count):
        at = base + i * attr_size
        _ns, name_index, raw_value = struct.unpack_from("<III", data, at)
        value_type = data[at + 15]
        (value_data,) = struct.unpack_from("<I", data, at + 16)

        name = _string(strings, name_index)
        if name not in wanted or wanted[name] is not None:
            continue

        if raw_value != 0xFFFFFFFF:
            wanted[name] = _string(strings, raw_value)
        elif value_type in (_TYPE_STRING,):
            wanted[name] = _string(strings, value_data)
        elif value_type == _TYPE_INT_DEC:
            wanted[name] = value_data


def _string(strings: list[str], index: int) -> Optional[str]:
    if index == 0xFFFFFFFF or index >= len(strings):
        return None
    return strings[index]


def _read_string_pool(data: bytes) -> list[str]:
    offset = 8
    while offset + 8 <= len(data):
        chunk_type, header_size, chunk_size = _chunk_header(data, offset)
        if chunk_size <= 0:
            return []
        if chunk_type == _CHUNK_STRING_POOL:
            return _decode_string_pool(data, offset, header_size)
        offset += chunk_size
    return []


def _decode_string_pool(data: bytes, offset: int, header_size: int) -> list[str]:
    count, _style_count, flags, strings_start, _styles_start = struct.unpack_from(
        "<IIIII", data, offset + 8
    )
    utf8 = bool(flags & _FLAG_UTF8)
    offsets_at = offset + header_size
    data_at = offset + strings_start

    result: list[str] = []
    for i in range(count):
        (relative,) = struct.unpack_from("<I", data, offsets_at + i * 4)
        result.append(_decode_string(data, data_at + relative, utf8))
    return result


def _decode_string(data: bytes, at: int, utf8: bool) -> str:
    if utf8:
        # Две длины подряд: в символах и в байтах. Каждая может занимать один
        # или два байта — старший бит первого означает «читай ещё один».
        at, _chars = _read_utf8_len(data, at)
        at, byte_length = _read_utf8_len(data, at)
        return data[at : at + byte_length].decode("utf-8", errors="replace")

    length = struct.unpack_from("<H", data, at)[0]
    at += 2
    if length & 0x8000:
        length = ((length & 0x7FFF) << 16) | struct.unpack_from("<H", data, at)[0]
        at += 2
    return data[at : at + length * 2].decode("utf-16-le", errors="replace")


def _read_utf8_len(data: bytes, at: int) -> tuple[int, int]:
    value = data[at]
    at += 1
    if value & 0x80:
        value = ((value & 0x7F) << 8) | data[at]
        at += 1
    return at, value


# --- контейнеры (XAPK) ------------------------------------------------------


def read_package_info(content: bytes) -> dict[str, Any]:
    """Что нам дали: одиночный APK или контейнер вроде XAPK.

    Google давно раздаёт приложения набором: базовый APK плюс «сплиты» под
    архитектуру процессора, плотность экрана и язык. Единого файла у таких
    приложений не существует, и сайты-зеркала упаковывают весь набор в архив.
    Ставится он одной транзакцией — Android это умеет, — но сначала нужно
    понять, что перед нами.

    @return package / version_name / version_code / kind ("apk" | "xapk") /
            parts (сколько APK внутри) / has_obb
    """
    single = read_apk_info(content)
    if single["package"]:
        return {**single, "kind": "apk", "parts": 1, "has_obb": False}

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = archive.namelist()
            parts = [n for n in names if n.lower().endswith(".apk")]
            if not parts:
                return {**single, "kind": None, "parts": 0, "has_obb": False}

            info = _container_manifest(archive) or _container_from_base(archive, parts)
            return {
                **info,
                "kind": "xapk",
                "parts": len(parts),
                "has_obb": any(n.lower().endswith(".obb") for n in names),
            }
    except Exception:
        return {**single, "kind": None, "parts": 0, "has_obb": False}


def _container_manifest(archive: zipfile.ZipFile) -> Optional[dict[str, Any]]:
    """Описание, которое кладут в архив сами упаковщики. Верить ему можно
    настолько, насколько оно совпадает с базовым APK, — но как источник имени
    и версии оно удобнее и надёжнее разбора чужих манифестов."""
    try:
        data = json.loads(archive.read("manifest.json").decode("utf-8"))
    except Exception:
        return None
    package = data.get("package_name")
    if not package:
        return None
    version_code = data.get("version_code")
    return {
        "package": str(package),
        "version_name": str(data["version_name"]) if data.get("version_name") else None,
        "version_code": int(version_code) if isinstance(version_code, (int, str)) and str(version_code).isdigit() else None,
    }


def _container_from_base(archive: zipfile.ZipFile, parts: list[str]) -> dict[str, Any]:
    """Описания нет — читаем манифесты вложенных APK и берём базовый.

    Базовый отличается тем, что несёт название версии: у сплитов его нет,
    только номер сборки.
    """
    fallback = {"package": None, "version_name": None, "version_code": None}
    for name in parts:
        info = read_apk_info(archive.read(name))
        if info["package"] and info["version_name"]:
            return info
        if info["package"] and fallback["package"] is None:
            fallback = info
    return fallback
