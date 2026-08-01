from decimal import Decimal

import pytest

from app.forms import LancamentoForm


def _monta_form(app, categorias, **campos):
    dados = {
        "descricao": "Teste",
        "data": "2026-03-01",
        "categoria_id": str(categorias["moradia"].id),
        **campos,
    }
    with app.test_request_context(method="POST", data=dados):
        form = LancamentoForm()
        form.carregar_categorias(list(categorias.values()))
        form.validate()
        return form


@pytest.mark.parametrize(
    ("digitado", "esperado"),
    [
        ("1234.56", Decimal("1234.56")),
        ("1.234,56", Decimal("1234.56")),
        ("1234,56", Decimal("1234.56")),
        ("R$ 1.234,56", Decimal("1234.56")),
        ("0,10", Decimal("0.10")),
    ],
)
def test_valor_aceita_formato_brasileiro_e_ingles(app, categorias, digitado, esperado):
    form = _monta_form(app, categorias, valor=digitado)

    assert form.valor.data == esperado
    assert not form.valor.errors


def test_valor_zero_e_recusado_com_mensagem_certa(app, categorias):
    """Zero não pode virar 'informe o valor' — o campo foi preenchido."""
    form = _monta_form(app, categorias, valor="0,00")

    assert "O valor deve ser maior que zero." in form.valor.errors


def test_valor_em_branco_pede_preenchimento(app, categorias):
    form = _monta_form(app, categorias, valor="")

    assert "Informe o valor." in form.valor.errors


def test_valor_negativo_e_recusado(app, categorias):
    form = _monta_form(app, categorias, valor="-10,00")

    assert form.valor.errors


def test_valor_com_texto_e_recusado(app, categorias):
    form = _monta_form(app, categorias, valor="abc")

    assert form.valor.errors


def test_descricao_obrigatoria(app, categorias):
    form = _monta_form(app, categorias, valor="10,00", descricao="")

    assert form.descricao.errors
