import json
from datetime import date

import pytest

from emporio.data_loader import load_store
from emporio.pricing import availability
from emporio.tools import (escalate_to_human, get_order_status, get_product,
search_products)

S = load_store()


def _customer_of(order_id):
    o = S.orders[S.orders.order_id == order_id].iloc[0]
    return S.customers[S.customers.customer_id == o.customer_id].iloc[0]


def _first_order(status):
    return int(S.orders[S.orders.status == status].order_id.iloc[0])


def test_search_returns_only_available_and_hides_stock():
    r = search_products(S, query="violão", max_price=1000)
    assert r["total_matches"] >= 1
    for it in r["items"]:
        row = S.products[S.products.product_id == it["product_id"]].iloc[0]
        assert availability(row.status, int(row.stock_quantity))[0]
        assert it["price_brl"] <= 1000
        assert "stock_quantity" not in it


def test_get_product_unavailable_has_reason_and_alternatives():
    row = S.products[S.products.status == "discontinued"].iloc[0]
    r = get_product(S, row["name"])
    assert r["available"] is False and r["reason"] == "discontinued"
    assert len(r["alternatives"]) <= 3
    assert all(a["product_id"] != row.product_id for a in r["alternatives"])


def test_get_product_not_found():
    assert get_product(S, "xyzzy inexistente") == {"error": "not_found"}


def test_order_ok_with_email_and_phone():
    oid = _first_order("delivered")
    c = _customer_of(oid)
    assert get_order_status(S, oid, c.email)["status"] == "delivered"
    assert get_order_status(S, oid, c.phone)["order_id"] == oid


def test_wrong_contact_and_missing_order_are_indistinguishable():
    oid = _first_order("delivered")
    wrong = get_order_status(S, oid, "errado@x.com")
    missing = get_order_status(S, 99999, "errado@x.com")
    assert wrong == missing and set(wrong) == {"error", "next"}


def test_cancelled_has_no_delay_count():
    oid = _first_order("cancelled")
    r = get_order_status(S, oid, _customer_of(oid).email)
    assert r["status"] == "cancelled" and r["days_since_estimated_delivery"] is None


def test_shipped_overdue_is_computed_in_code():
    oid = _first_order("shipped")
    r = get_order_status(S, oid, _customer_of(oid).email, as_of=date(2026, 11, 2))
    assert r["overdue"] is True and r["days_since_estimated_delivery"] > 0


def test_escalation_appends_jsonl(tmp_path):
    p = tmp_path / "esc.jsonl"
    r = escalate_to_human("complaint", "teste", path=p)
    rec = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
    assert rec["ticket_id"] == r["ticket_id"] and r["expected_return"] == "24 horas úteis"
    with pytest.raises(ValueError):
        escalate_to_human("outro", "x", path=p)