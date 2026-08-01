"""Filtros Jinja para formatação brasileira."""

from datetime import date
from decimal import Decimal

MESES = [
    "jan", "fev", "mar", "abr", "mai", "jun",
    "jul", "ago", "set", "out", "nov", "dez",
]  # fmt: skip


def moeda(valor: Decimal | float | None) -> str:
    """1234.5 -> 'R$ 1.234,50'. Negativos viram '-R$ 1.234,50'."""
    if valor is None:
        return "R$ 0,00"

    valor = Decimal(str(valor)).quantize(Decimal("0.01"))
    sinal = "-" if valor < 0 else ""

    # Formata com separadores ingleses e troca: 1,234.50 -> 1.234,50
    corpo = f"{abs(valor):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{sinal}R$ {corpo}"


def data_br(valor: date | None) -> str:
    return valor.strftime("%d/%m/%Y") if valor else ""


def mes_abrev(numero: int) -> str:
    return MESES[numero - 1]


def registrar(app) -> None:
    app.jinja_env.filters["moeda"] = moeda
    app.jinja_env.filters["data_br"] = data_br
    app.jinja_env.filters["mes_abrev"] = mes_abrev
