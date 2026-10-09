from app.utils.schedule_codes import build_code_index, canonical_code, code_key

INDEX = build_code_index(["Ох", "Оз", "М", "Гп", "Ц", "А"])


def test_case_and_spaces_ignored():
    for raw in ("Ох", "ох", "ОХ", "оХ", " Ох ", "О х"):
        assert canonical_code(raw, INDEX) == "Ох"
    assert canonical_code("гп", INDEX) == "Гп"


def test_latin_lookalikes_map_to_cyrillic():
    # Латинские O/x, M, A — раскладку не переключили.
    assert canonical_code("Ox", INDEX) == "Ох"
    assert canonical_code("OX", INDEX) == "Ох"
    assert canonical_code("M", INDEX) == "М"
    assert canonical_code("A", INDEX) == "А"


def test_unknown_and_empty_kept():
    assert canonical_code("Вых", INDEX) == "Вых"
    assert canonical_code("  б/л ", INDEX) == "б/л"
    assert canonical_code(None, INDEX) == ""
    assert canonical_code("", INDEX) == ""


def test_code_key_equal_for_variants():
    assert code_key("ОХ") == code_key("ox") == code_key("Ох")
