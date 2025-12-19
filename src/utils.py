import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional

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
    if field_type in _STRING_FIELD_TYPES:
        return _ensure_string(value)
    if field_type in _INTEGER_FIELD_TYPES:
        return _coerce_int(value)
    if field_type in _FLOAT_FIELD_TYPES:
        return _coerce_float(value)
    if field_type in _DATETIME_FIELD_TYPES:
        return _parse_datetime_value(value)
    if field_type in _DATE_FIELD_TYPES:
        return _parse_date_value(value)
    if field_type == "boolean":
        return bool(value) if not _is_null(value) else False
    if isinstance(value, (list, dict)):
        return _stringify_complex(value)
    if value is False:
        return None
    return value


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
    if field_type in _STRING_FIELD_TYPES or field_type in _RELATION_ID_TYPES | _RELATION_LIST_TYPES:
        return pl.Utf8
    if field_type in _INTEGER_FIELD_TYPES:
        return pl.Int64
    if field_type in _FLOAT_FIELD_TYPES:
        return pl.Float64
    if field_type == "boolean":
        return pl.Boolean
    if field_type in _DATETIME_FIELD_TYPES or field_type in _DATE_FIELD_TYPES:
        return pl.Datetime(time_unit="us")
    return None


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
