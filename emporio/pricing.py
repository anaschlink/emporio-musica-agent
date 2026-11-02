from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")

# (maximum tier, minimum installment amount), according to section 3.1 of the manual
_TIERS = ((3, Decimal("50")), (6, Decimal("80")), (12, Decimal("100")))

def money(value) -> Decimal:
    """Convert to Decimal via str to avoid inheriting floating-position errors"""
    return Decimal(str(value))

def q(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)

def _min_installment(n: int) -> Decimal:
    for upper, minimum in _TIERS:
        if n <= upper:
            return minimum
    raise ValueError(n)

def installments(price) -> tuple[int, Decimal]:
    """Find the largest n (12..1) for which the installment meets its tier minimum. n=1 always applies."""
    total = money(price)
    for n in range(12, 1, -1):
        if total / n >= _min_installment(n):
            return n, q(total / n)
    return 1, q(total)


def active_promotion(promotions, product_id: int) -> dict | None:
    """A promotion is active when is_active == 1. The data contains no dates.
    If multiple promotions are active, use the one with the highest discount
    (an assumption; currently, each product has at most one active promotion).
    """
    rows = promotions[(promotions.product_id == product_id) & promotions.is_active]
    if rows.empty:
        return None
    return {"discount_pct": int(rows.discount_percent.max())}


def availability(status: str, stock: int) -> tuple[bool, str | None]:
    if status == "discontinued":
        return False, "discontinued"
    if status == "coming_soon":
        return False, "coming_soon"
    if status == "active" and stock > 0:
        return True, None
    return False, "out_of_stock"


def price_info(price_brl, promo: dict | None) -> dict:
    """Calculate the effective price, PIX price, and installments.
    The 5% PIX discount applies only when there is no active promotion (section 6.2).
    Installments are calculated using the effective price (an assumption documented in the README).
    """
    original = money(price_brl)
    if promo:
        promo_price = q(original * (Decimal(100) - promo["discount_pct"]) / 100)
        effective = promo_price
        promo_out = {"original": float(original), "promo_price": float(promo_price),
                     "discount_pct": promo["discount_pct"]}
        pix = None
    else:
        effective = original
        promo_out = None
        pix = float(q(original * Decimal("0.95")))
    n, value = installments(effective)
    return {"price_brl": float(effective), "promo": promo_out, "pix_price": pix,
            "max_installments": n, "installment_value": float(value)}