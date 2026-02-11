import json
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Dict, Iterable, List, Optional

import polars as pl

_STRING_FIELD_TYPES = {
    "char",
    "text",
    "html",
    "selection",
    "reference",
    "binary",
    "json",
}
_RELATION_LIST_TYPES = {"one2many", "many2many"}
_RELATION_ID_TYPES = {"many2one"}
_FLOAT_FIELD_TYPES = {"float", "monetary"}
_INTEGER_FIELD_TYPES = {"integer"}
_DATETIME_FIELD_TYPES = {"datetime"}
_DATE_FIELD_TYPES = {"date"}


def _is_null(value: Any) -> bool:
    return value is None or value is False


def _stringify_complex(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return str(value)


def _ensure_string(value: Any) -> Optional[str]:
    if _is_null(value):
        return None
    if isinstance(value, (list, dict)):
        return _stringify_complex(value)
    return str(value)


def _coerce_many2one(value: Any) -> Optional[str]:
    if _is_null(value):
        return None
    relation_id: Optional[Any] = None

    if isinstance(value, (list, tuple)) and value:
        relation_id = value[0]
    elif isinstance(value, dict):
        relation_id = value.get("id")
    else:
        relation_id = value

    if relation_id is None or relation_id is False:
        return None
    return str(relation_id)


def _coerce_relation_list(value: Any) -> Optional[str]:
    if _is_null(value):
        return None
    if isinstance(value, (list, tuple, set)):
        return _stringify_complex(list(value))
    if isinstance(value, dict):
        return _stringify_complex(value)
    return str(value)


def _coerce_int(value: Any) -> Optional[int]:
    if _is_null(value):
        return None
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> Optional[float]:
    if _is_null(value):
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_datetime_value(value: Any) -> Optional[datetime]:
    if _is_null(value):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
    return None


def _parse_date_value(value: Any) -> Optional[datetime]:
    if _is_null(value):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
            try:
                parsed = datetime.strptime(value, fmt)
                return parsed.replace(
                    hour=parsed.hour or 0,
                    minute=parsed.minute or 0,
                    second=parsed.second or 0,
                    microsecond=parsed.microsecond or 0,
                )
            except ValueError:
                continue
    return None


def _coerce_value(field_type: Optional[str], value: Any) -> Any:
    if field_type in _RELATION_ID_TYPES:
        return _coerce_many2one(value)
    if field_type in _RELATION_LIST_TYPES:
        return _coerce_relation_list(value)
    return _ensure_string(value)


def _python_type_name(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, Decimal):
        return "decimal"
    if isinstance(value, datetime):
        return "datetime"
    if isinstance(value, str):
        return "str"
    if isinstance(value, dict):
        return "dict"
    if isinstance(value, (list, tuple, set)):
        return "list"
    return type(value).__name__


def detect_mixed_type_columns(
    records: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """
    Detecta colunas que contêm múltiplos tipos Python no mesmo batch.

    Retorna um dict no formato:
    {
        "coluna": {
            "types": ["int", "str"],
            "incoherent_count": 3,
        }
    }
    """
    type_counters: Dict[str, Counter] = defaultdict(Counter)
    for record in records:
        for key, value in record.items():
            if _is_null(value):
                continue
            type_counters[key][_python_type_name(value)] += 1

    mixed_columns: Dict[str, Dict[str, Any]] = {}
    for column, counter in type_counters.items():
        if len(counter) <= 1:
            continue
        total_values = sum(counter.values())
        dominant_count = max(counter.values())
        mixed_columns[column] = {
            "types": sorted(counter.keys()),
            "incoherent_count": total_values - dominant_count,
        }
    return mixed_columns


def ensure_string_columns(
    df: pl.DataFrame,
    *,
    on_cast_warning: Optional[Callable[[str, pl.DataType], None]] = None,
) -> pl.DataFrame:
    """
    Garante que todas as colunas sejam Utf8.

    Quando uma coluna precisar de cast, chama `on_cast_warning(col, original_dtype)`.
    """
    for column in df.columns:
        original_dtype = df.schema[column]
        if original_dtype in {pl.Utf8, pl.Categorical}:
            continue
        if on_cast_warning:
            on_cast_warning(column, original_dtype)
        try:
            df = df.with_columns(pl.col(column).cast(pl.Utf8, strict=False).alias(column))
        except Exception:
            df = df.with_columns(
                pl.col(column)
                .map_elements(
                    lambda value: None if value is None else str(value),
                    return_dtype=pl.Utf8,
                )
                .alias(column)
            )
    return df


def sanitize_records(
    records: List[Dict[str, Any]],
    fields_metadata: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Normaliza valores usando o schema do Odoo para garantir tipos consistentes."""
    normalized_records: List[Dict[str, Any]] = []
    for record in records:
        normalized: Dict[str, Any] = {}
        for key, value in record.items():
            metadata = fields_metadata.get(key) or {}
            normalized[key] = _coerce_value(metadata.get("type"), value)
        normalized_records.append(normalized)
    return normalized_records


def _map_field_type_to_polars(field_type: Optional[str]) -> Optional[pl.DataType]:
    # Forca persistencia uniforme em string para todos os campos no parquet.
    return pl.Utf8


def build_polars_schema(
    fields_metadata: Dict[str, Dict[str, Any]],
    selected_fields: Optional[Iterable[str]] = None,
) -> Dict[str, pl.DataType]:
    schema: Dict[str, pl.DataType] = {}
    fields = selected_fields or fields_metadata.keys()
    for field in fields:
        metadata = fields_metadata.get(field)
        if not metadata:
            continue
        dtype = _map_field_type_to_polars(metadata.get("type"))
        if dtype is not None:
            schema[field] = dtype
    return schema


def enforce_polars_schema(
    df: pl.DataFrame,
    schema: Dict[str, pl.DataType],
) -> pl.DataFrame:
    if not schema:
        return df

    casts = [
        pl.col(column).cast(dtype, strict=False)
        for column, dtype in schema.items()
        if column in df.columns
    ]
    if not casts:
        return df

    return df.with_columns(casts)
