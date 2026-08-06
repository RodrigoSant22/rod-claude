"""Filtros Jinja de formatação brasileira."""

from datetime import date
from decimal import Decimal

import pytest

from app.filters import data_br, mes_abrev, moeda


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        (Decimal("0.00"), "R$ 0,00"),
        (Decimal("1234.50"), "R$ 1.234,50"),
        (Decimal("1000000.00"), "R$ 1.000.000,00"),
        (Decimal("-1800.00"), "-R$ 1.800,00"),
        (Decimal("0.10"), "R$ 0,10"),
        (None, "R$ 0,00"),
    ],
)
def test_moeda_formata_no_padrao_brasileiro(entrada, esperado):
    assert moeda(entrada) == esperado


def test_data_br():
    assert data_br(date(2026, 3, 5)) == "05/03/2026"
    assert data_br(None) == ""


def test_mes_abrev():
    assert mes_abrev(1) == "jan"
    assert mes_abrev(12) == "dez"
