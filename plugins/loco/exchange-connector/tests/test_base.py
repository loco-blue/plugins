import pytest

from adapters.base import ExchangeAdapter, FuturesAdapter


def test_exchange_adapter_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        ExchangeAdapter(client=None, credentials={})


def test_futures_adapter_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        FuturesAdapter(client=None, credentials={})


def test_futures_adapter_is_an_exchange_adapter():
    assert issubclass(FuturesAdapter, ExchangeAdapter)
