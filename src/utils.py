import json
from collections import defaultdict
from typing import Any, Dict, List


def _normalize_value(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)
    return value


def _infer_field_types(records: List[Dict[str, Any]]):
    field_types = defaultdict(set)
    for record in records:
        for key, value in record.items():
            if value is None:
                continue
            field_types[key].add(type(value))
    return field_types


def sanitize_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normaliza valores retornados do Odoo para evitar mixed types em colunas."""
    normalized_records = []
    for record in records:
        normalized = {key: _normalize_value(val) for key, val in record.items()}
        normalized_records.append(normalized)

    field_types = _infer_field_types(normalized_records)
    fields_to_string = {
        field
        for field, types in field_types.items()
        if len(types - {type(None)}) > 1 or (str in types and (types - {str, type(None)}))
    }

    if not fields_to_string:
        return normalized_records

    coerced_records = []
    for record in normalized_records:
        coerced = {}
        for key, value in record.items():
            if key in fields_to_string and value is not None:
                coerced[key] = str(value)
            else:
                coerced[key] = value
        coerced_records.append(coerced)

    return coerced_records
