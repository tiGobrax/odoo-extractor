#!/usr/bin/env python3
import argparse
import os
import tempfile
from typing import Dict, List, Optional, Set

import polars as pl
from google.cloud import storage
from loguru import logger

_storage_client: Optional[storage.Client] = None
_DEFAULT_BUCKET = "gobrax-data-lake"
_DEFAULT_BASE_PATH = "data-lake/odoo"


def _get_storage_client() -> storage.Client:
    global _storage_client
    if _storage_client is None:
        _storage_client = storage.Client()
    return _storage_client


def _normalize_base_path(value: str) -> str:
    return value.strip("/").rstrip("/")


def _find_keyword_fields(
    columns: List[str],
    keywords: List[str],
    ignored_fields: Set[str],
) -> List[str]:
    lowered = [kw.lower() for kw in keywords if kw]
    if not lowered:
        return []

    matched: List[str] = []
    for column in columns:
        if column in ignored_fields:
            continue
        col_lower = column.lower()
        if any(term in col_lower for term in lowered):
            matched.append(column)
    return matched


def discover_models(bucket_name: str, base_path: str) -> List[str]:
    client = _get_storage_client()
    prefix = f"{_normalize_base_path(base_path)}/"

    models: Set[str] = set()
    iterator = client.list_blobs(bucket_name, prefix=prefix, delimiter="/")
    for page in iterator.pages:
        for found in page.prefixes:
            normalized = found[len(prefix) :].strip("/")
            if normalized:
                models.add(normalized)

    return sorted(models)


def pick_latest_blob(bucket_name: str, model: str, base_path: str):
    client = _get_storage_client()
    prefix = f"{_normalize_base_path(base_path)}/{model}/"

    latest_blob = None
    for blob in client.list_blobs(bucket_name, prefix=prefix):
        if not blob.name.endswith(".parquet"):
            continue
        if latest_blob is None or blob.name > latest_blob.name:
            latest_blob = blob
    return latest_blob


def _compute_field_stats(df: pl.DataFrame, field: str) -> Dict[str, object]:
    if field not in df.columns:
        return {"available": False}

    series = df.get_column(field)
    total = series.len()
    if total == 0:
        return {
            "available": True,
            "total": 0,
            "null_pct": 0.0,
            "min": None,
            "max": None,
        }

    nulls = series.null_count()
    null_pct = (nulls / total) * 100 if total else 0.0
    not_null = total - nulls

    non_null_series = series.drop_nulls() if not_null else None
    min_val = non_null_series.min() if non_null_series is not None else None
    max_val = non_null_series.max() if non_null_series is not None else None

    return {
        "available": True,
        "total": total,
        "null_pct": null_pct,
        "min": str(min_val) if min_val is not None else None,
        "max": str(max_val) if max_val is not None else None,
    }


def analyze_blob(blob, fields: List[str]) -> Dict[str, object]:
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
        temp_path = tmp.name

    try:
        blob.download_to_filename(temp_path)
        df = pl.read_parquet(temp_path)
    finally:
        try:
            os.remove(temp_path)
        except FileNotFoundError:
            pass

    stats = {
        field: _compute_field_stats(df, field)
        for field in fields
    }

    return {
        "rows": df.height,
        "stats": stats,
    }


def analyze_blob(
    blob,
    base_fields: List[str],
    keyword_terms: List[str],
    ignored_fields: Set[str],
) -> Dict[str, object]:
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
        temp_path = tmp.name

    try:
        blob.download_to_filename(temp_path)
        df = pl.read_parquet(temp_path)
    finally:
        try:
            os.remove(temp_path)
        except FileNotFoundError:
            pass

    keyword_fields = _find_keyword_fields(df.columns, keyword_terms, ignored_fields)

    ordered_fields: List[str] = []
    seen: Set[str] = set()

    def add_field(field: str) -> None:
        if field in ignored_fields:
            return
        if field not in seen:
            ordered_fields.append(field)
            seen.add(field)

    for field in base_fields:
        if field in ignored_fields:
            continue
        add_field(field)
    for field in keyword_fields:
        add_field(field)

    stats = {
        field: _compute_field_stats(df, field)
        for field in ordered_fields
    }

    return {
        "rows": df.height,
        "stats": stats,
        "keyword_fields": keyword_fields,
    }


def _print_field_line(field: str, stats: Dict[str, Dict[str, object]]) -> None:
    field_stats = stats.get(field)
    if not field_stats:
        print(f"  - {field}: ⚠️ estatística indisponível")
        return

    if not field_stats["available"]:
        print(f"  - {field}: ❌ campo ausente no arquivo analisado")
        return

    null_pct = field_stats["null_pct"]
    min_val = field_stats["min"] or "-"
    max_val = field_stats["max"] or "-"
    print(
        f"  - {field}: nulls={null_pct:.2f}% "
        f"| min={min_val} | max={max_val}"
    )


def print_report(
    model: str,
    bucket: str,
    blob,
    result: Dict[str, object],
    base_fields: List[str],
) -> None:
    stats = result["stats"]
    selected_fields = sorted(stats.keys())

    print(f"\nmodel: {model}")
    print("campos:")
    if not selected_fields:
        print("  - nenhum campo com os termos especificados")
        return

    for field in selected_fields:
        _print_field_line(field, stats)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analisa amostras Parquet para decidir write_date vs __last_update."
    )
    parser.add_argument(
        "--bucket",
        default=_DEFAULT_BUCKET,
        help=f"Nome do bucket no GCS (default: {_DEFAULT_BUCKET}).",
    )
    parser.add_argument(
        "--base-path",
        default=_DEFAULT_BASE_PATH,
        help=f"Prefixo base dentro do bucket (default: {_DEFAULT_BASE_PATH}).",
    )
    parser.add_argument(
        "--models",
        nargs="*",
        help="Lista de models para analisar. Se vazio, detecta automaticamente.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limita a quantidade de models analisados.",
    )
    parser.add_argument(
        "--fields",
        nargs="*",
        default=[],
        help="Campos fixos a serem analisados. Se vazio, nenhum campo fixo é exibido.",
    )
    parser.add_argument(
        "--search-terms",
        nargs="+",
        default=["last", "update", "write", "create", "date"],
        help="Palavras que serão usadas para descobrir campos adicionais (case insensitive).",
    )
    parser.add_argument(
        "--ignore-fields",
        nargs="*",
        default=[
            "create_uid",
            "write_uid",
            "picking_type_use_create_lots",
            "created_purchase_line_ids",
            "last_delivery_partner_id",
            "can_write",
        ],
        help="Campos ignorados mesmo que apareçam nos termos.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.bucket:
        raise SystemExit("Bucket não informado. Use --bucket para definir o destino.")

    if args.models:
        models = args.models
    else:
        logger.info("🔍 Descobrindo models a partir do bucket...")
        models = discover_models(args.bucket, args.base_path)
        if not models:
            raise SystemExit("Nenhum model encontrado no bucket.")

    if args.limit:
        models = models[: args.limit]

    ignored_fields = set(args.ignore_fields or [])
    base_fields = [field for field in (args.fields or []) if field not in ignored_fields]

    logger.info(
        f"🗂️ Analisando {len(models)} models em gs://{args.bucket}/{_normalize_base_path(args.base_path)}"
    )

    for model in models:
        try:
            blob = pick_latest_blob(args.bucket, model, args.base_path)
            if not blob:
                logger.warning(f"⚠️ Nenhum parquet encontrado para {model}")
                continue

            result = analyze_blob(
                blob,
                base_fields=base_fields,
                keyword_terms=args.search_terms,
                ignored_fields=ignored_fields,
            )
            print_report(
                model,
                args.bucket,
                blob,
                result,
                base_fields,
            )

        except Exception as exc:
            logger.error(f"❌ Falha ao analisar {model}: {exc}")


if __name__ == "__main__":
    main()
