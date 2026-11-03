from __future__ import annotations

import difflib
import json
import os
import unicodedata
import uuid
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from .data_loader import Store, normalize_phone, normalize_email
from .pricing import active_promotion, availability, price_info

ESCALATIONS_PATH = Path(__file__).resolve().parent.parent / "escalations.jsonl"
ESCALATION_KINDS = {"complaint", "policy_doubt", "customer_request"}
FAILED = {"error": "verification_failed", "next": "ask_customer_for_email_or_phone"}

def today() -> date:
    v = os.getenv("AS_OF")
    return date.fromisoformat(v) if v else datetime.now(ZoneInfo("America/Campo_Grande")).date()

def _norm(s) -> str:
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()

def _stem(tok: str) -> str:
    if tok.endswith("oes"):
        return tok[:-3] + "ao"
    if len(tok) > 3 and tok.endswith("s"):
        return tok[:-1]
    return tok

def _tokens(text: str) -> list[str]:
    return [_stem(t) for t in _norm(text).replace("-", " ").split() if t]

def _category_matches(category: str, cat_name: str) -> bool:
    cat_tokens = _tokens(cat_name)
    return all(t in cat_tokens for t in _tokens(category))

def _category_name(store: Store, category_id) -> str | None:
    c = store.categories.loc[store.categories.category_id == category_id, "name"]
    return c.iloc[0] if len(c) else None


def _view(store: Store, row) -> dict:
    pid = int(row["product_id"])
    info = price_info(row["price_brl"], active_promotion(store.promotions, pid))
    return {"product_id": pid, "name": row["name"],
            "category": _category_name(store, row["category_id"]), **info}


def _is_available(row) -> bool:
    return availability(row["status"], int(row["stock_quantity"]))[0]


def search_products(store: Store, query: str | None = None, category: str | None = None,min_price: float | 
                    None = None, max_price: float | None = None,limit: int = 6) -> dict:
    limit = 6 if limit is None else max(1, min(int(limit), 6))
    items = []

    if category and not any(
        _category_matches(category, name) for name in store.categories["name"]
    ):
        return {
            "error": "unknown_category",
            "category": category,
            "available_categories": store.categories["name"].tolist(),
            "hint": "Retry with a valid category, or omit it and use query."
        }
    for _, row in store.products.iterrows():
        if not _is_available(row):
            continue
        cat = _category_name(store, row["category_id"]) or ""
        hay = _norm(f'{row["name"]} {row["description"]} {cat}').replace("-", " ").split()
        if query and not all(any(w.startswith(t) for w in hay) for t in _tokens(query)):
            continue
        if category and not _category_matches(category, cat):
            continue
        v = _view(store, row)
        if min_price is not None and v["price_brl"] < min_price:
            continue
        if max_price is not None and v["price_brl"] > max_price:
            continue
        items.append(v)
    items.sort(key=lambda v: v["price_brl"])
    return {"total_matches": len(items), "items": items[:limit]}


def _alternatives(store: Store, row, n: int = 3) -> list[dict]:
    p = store.products
    same = p[(p.category_id == row["category_id"]) & (p.product_id != row["product_id"])]
    cands = [_view(store, r) for _, r in same.iterrows() if _is_available(r)]
    cands.sort(key=lambda v: abs(v["price_brl"] - float(row["price_brl"])))
    return cands[:n]


def get_product(store: Store, name: str) -> dict:
    p = store.products
    target = _norm(name).strip()
    toks = _tokens(name)
    if not toks:
        return {"error": "not_found"}
    names_norm = p["name"].map(_norm)
    exact = p[names_norm == target]
    if len(exact) == 1:
        hit = exact
    else:
        hit = p[names_norm.map(lambda n: all(any(w.startswith(t) for w in n.replace("-", " ").split())
        for t in toks))]
        if hit.empty:
            close = difflib.get_close_matches(target, names_norm.tolist(), n=2, cutoff=0.6)
            hit = p[names_norm.isin(close)]
    if hit.empty:
        return {"error": "not_found"}
    if len(hit) > 1:
        return {"error": "ambiguous",
                "candidates": [{"product_id": int(r["product_id"]), "name": r["name"]}
                               for _, r in hit.head(5).iterrows()]}
    row = hit.iloc[0]
    ok, reason = availability(row["status"], int(row["stock_quantity"]))
    out = {**_view(store, row), "available": ok, "status": row["status"]}
    if not ok:
        out["reason"] = reason
        out["alternatives"] = _alternatives(store, row)
    return out


def _contact_matches(customer, given: str) -> bool:
    given = (given or "").strip()
    if "@" in given:
        return normalize_email(given) == customer["email_norm"]
    digits, stored = normalize_phone(given), customer["phone_digits"]
    return len(stored) >= 10 and digits.endswith(stored)


def get_order_status(store: Store, order_id, email_or_phone: str,
                     as_of: date | None = None) -> dict:
    try:
        oid = int(str(order_id).strip().lstrip("#"))
    except ValueError:
        return dict(FAILED)
    orders = store.orders[store.orders.order_id == oid]
    if orders.empty:
        return dict(FAILED)
    o = orders.iloc[0]
    cust = store.customers[store.customers.customer_id == o["customer_id"]]
    if cust.empty or not _contact_matches(cust.iloc[0], email_or_phone):
        return dict(FAILED)

    names = store.products.set_index("product_id")["name"]
    items = [{"product_id": int(r.product_id), "name": names.get(r.product_id),
              "quantity": int(r.quantity)}
             for r in store.order_items[store.order_items.order_id == oid].itertuples()]

    ref_date = as_of or today()
    est = o["estimated_delivery"]
    est = None if pd.isna(est) else est
    pending = o["status"] in {"pending", "confirmed", "shipped"}
    days = ref_date.toordinal() - est.toordinal() if (est and pending) else None

    order_date = o["order_date"]
    order_date = None if pd.isna(order_date) else order_date
    days_since_order = (
        ref_date.toordinal() - order_date.toordinal() if order_date else None
    )

    tracking = None if pd.isna(o["tracking_code"]) else o["tracking_code"]
    return {"order_id": oid, "status": o["status"], "items": items,
            "total_brl": float(o["total_brl"]), "payment_method": o["payment_method"],
            "order_date": order_date.isoformat() if order_date else None,
            "days_since_order": days_since_order,
            "within_defect_window_30d": (
                days_since_order <= 30 if days_since_order is not None else None
            ),
            "estimated_delivery": est.isoformat() if est else None,
            "days_since_estimated_delivery": days,
            "overdue": bool(days is not None and days > 0),
            "tracking_code": tracking}

def escalate_to_human(kind: str, summary: str, contact: str | None = None,
                      path: Path = ESCALATIONS_PATH) -> dict:
    if kind not in ESCALATION_KINDS:
        raise ValueError(f"kind inválido: {kind}")
    ticket = uuid.uuid4().hex[:8]
    rec = {"ticket_id": ticket, "kind": kind, "summary": summary, "contact": contact,
           "created_at": datetime.now(ZoneInfo("America/Campo_Grande")).isoformat()}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return {"ticket_id": ticket, "expected_return": "24 horas úteis"}