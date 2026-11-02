from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

REQUIRED = {
    "categories": {"category_id", "name", "description"},
    "customers": {"customer_id", "name", "phone", "email", "city"},
    "order_items": {"order_id", "quantity", "product_id"},
    "orders": {"order_id", "customer_id", "order_date", "status", "total_brl","payment_method", "tracking_code", "estimated_delivery", "notes"},
    "products": {"product_id", "price_brl", "name", "category_id", "description","stock_quantity", "status", "specs", "created_at"},
    "promotions": {"promotion_id", "product_id", "discount_percent","description", "is_active"},
}

@dataclass(frozen=True)
class Store:
    categories: pd.DataFrame
    customers: pd.DataFrame
    order_items: pd.DataFrame
    orders: pd.DataFrame
    products: pd.DataFrame
    promotions: pd.DataFrame

def normalize_phone(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")

def normalize_email(value: str | None ) -> str:
    return (value or "").strip().lower()

def _parse_specs(raw) -> dict:
    if not isinstance(raw, str):
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}

def _read(data_dir: Path, name: str, **kwargs) -> pd.DataFrame:
    path = data_dir / f"{name}.csv"
    df = pd.read_csv(path, encoding="utf-8", **kwargs)
    missing = REQUIRED[name] - set(df.columns)
    if missing:
        raise ValueError (f"{path.name}: colunas ausentes {sorted(missing)}")
    return df


def load_store(data_dir: Path = DATA_DIR) -> Store:
    categories = _read(data_dir, "categories")

    customers = _read(data_dir, "customers", dtype={"phone": str, "email": str})
    customers["phone_digits"] = customers["phone"].map(normalize_phone)
    customers["email_norm"] = customers["email"].map(normalize_email)

    order_items = _read(data_dir, "order_items")

    orders = _read(data_dir, "orders", dtype={"tracking_code": str})
    orders["order_date"] = pd.to_datetime(orders["order_date"]).dt.date
    orders["estimated_delivery"] = pd.to_datetime(orders["estimated_delivery"]).dt.date

    products = _read(data_dir, "products")
    products["specs"] = products["specs"].map(_parse_specs)
    products["created_at"] = pd.to_datetime(products["created_at"]).dt.date

    promotions = _read(data_dir, "promotions")
    promotions["is_active"] = promotions["is_active"].astype(int).astype(bool)

    return Store(categories, customers, order_items, orders, products, promotions)