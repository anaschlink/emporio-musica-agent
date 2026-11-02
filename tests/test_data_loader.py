from emporio.data_loader import load_store, normalize_email, normalize_phone

def test_row_counts():
    s = load_store()
    assert len(s.categories) == 9
    assert len(s.customers) == 50
    assert len(s.order_items) == 22
    assert len(s.orders) == 20
    assert len(s.products) == 65
    assert len(s.promotions) == 25


def test_normalization():
    assert normalize_phone("(67) 99812-3456") == "67998123456"
    assert normalize_email("  Lucas.Mendes@JMAIL.com ") == "lucas.mendes@jmail.com"


def test_specs_parsed_to_dict():
    s = load_store()
    assert s.products.loc[s.products.product_id == 81, "specs"].iloc[0]["strings"] == "nylon"