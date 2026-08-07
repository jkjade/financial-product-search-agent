import pytest
from pydantic import ValidationError

from src.api.models import ProductSearchRequest


def test_structured_agent_search_request():
    request = ProductSearchRequest(
        product_type="OVERSEAS_ETF",
        region="United States",
        max_fee="0.05",
        sort_by="fee",
        order="asc",
        limit=3,
    )
    assert request.product_type == "OVERSEAS_ETF"
    assert str(request.max_fee) == "0.05"
    assert request.limit == 3


def test_search_request_rejects_unsafe_page_size():
    with pytest.raises(ValidationError):
        ProductSearchRequest(limit=101)


def test_search_request_rejects_unknown_product_type():
    with pytest.raises(ValidationError):
        ProductSearchRequest(product_type="STOCK")
