from decimal import Decimal
import pandas as pd
import pytest
from emporio.pricing import installments, price_info, availability, active_promotion

@pytest.mark.parametrize("price,expected", [
    (1000, (10, Decimal("100.00"))),
    (400, (5, Decimal("80.00"))),
    (150, (3, Decimal("50.00"))),
    (120, (2, Decimal("60.00"))),
    (49, (1, Decimal("49.00"))),
    (600, (6, Decimal("100.00"))),
    (700, (7, Decimal("100.00"))),
])

def test_installments(price, expected):
    assert installments(price) == expected


def test_pix_only_without_promo():
    assert price_info(1000, None)["pix_price"] == 950.0
    assert price_info(1000, {"discount_pct": 20})["pix_price"] is None


def test_promo_price_and_installments_on_effective_price():
    info = price_info(1000, {"discount_pct": 20})
    assert info["promo"] == {"original": 1000.0, "promo_price": 800.0, "discount_pct": 20}
    assert info["price_brl"] == 800.0
    assert (info["max_installments"], info["installment_value"]) == (8, 100.0)


@pytest.mark.parametrize("status,stock,expected", [
    ("active", 5, (True, None)),
    ("active", 0, (False, "out_of_stock")),
    ("discontinued", 13, (False, "discontinued")),
    ("coming_soon", 2, (False, "coming_soon")),
])
def test_availability(status, stock, expected):
    assert availability(status, stock) == expected


def test_active_promotion_ignores_inactive():
    promos = pd.DataFrame({"product_id": [96, 96, 90], "discount_percent": [18, 40, 10],
                           "is_active": [False, False, True]})
    assert active_promotion(promos, 96) is None
    assert active_promotion(promos, 90) == {"discount_pct": 10}