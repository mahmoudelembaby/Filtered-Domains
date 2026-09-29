import pytest
from app.utils.domain import normalize_domain


def test_normalize_variants():
    for raw in ["https://www.example.com/", "http://example.com", "https://example.com", "example.com",
                "WWW.EXAMPLE.COM", "example.com/"]:
        assert normalize_domain(raw) == "example.com"


def test_keep_subdomain():
    assert normalize_domain("https://mail.example.com/x") == "mail.example.com"
    assert normalize_domain("a.b.example.com") == "a.b.example.com"


def test_invalid():
    for bad in ["", "localhost", "http://localhost:8000", "internal", "a..b.com"]:
        with pytest.raises(ValueError):
            normalize_domain(bad)
