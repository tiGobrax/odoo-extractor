import polars as pl

from src.utils import detect_mixed_type_columns, ensure_string_columns


def test_detect_mixed_type_columns_numeric_only() -> None:
    records = [
        {"valor": 100},
        {"valor": 200},
        {"valor": 300},
    ]

    mixed = detect_mixed_type_columns(records)

    assert mixed == {}


def test_detect_mixed_type_columns_numeric_and_string() -> None:
    records = [
        {"valor": 100},
        {"valor": "CAN"},
        {"valor": 200},
    ]

    mixed = detect_mixed_type_columns(records)

    assert "valor" in mixed
    assert mixed["valor"]["types"] == ["int", "str"]
    assert mixed["valor"]["incoherent_count"] == 1


def test_detect_mixed_type_columns_string_only() -> None:
    records = [
        {"valor": "A"},
        {"valor": "B"},
        {"valor": "C"},
    ]

    mixed = detect_mixed_type_columns(records)

    assert mixed == {}


def test_ensure_string_columns_casts_numeric_columns() -> None:
    df = pl.DataFrame({"id": [1, 2, 3], "valor": ["100", "CAN", "200"]})
    casted = []

    out = ensure_string_columns(
        df,
        on_cast_warning=lambda column, dtype: casted.append((column, str(dtype))),
    )

    assert out.schema["id"] == pl.Utf8
    assert out.schema["valor"] == pl.Utf8
    assert casted == [("id", "Int64")]
    assert out["id"].to_list() == ["1", "2", "3"]
