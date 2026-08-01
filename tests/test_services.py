from datetime import date
from decimal import Decimal

from app import services
from app.models import TipoLancamento


def test_resumo_soma_receitas_e_despesas(app, lancamentos):
    resumo = services.calcular_resumo()

    assert resumo.receitas == Decimal("5000.00")
    assert resumo.despesas == Decimal("3664.90")
    assert resumo.saldo == Decimal("1335.10")


def test_resumo_respeita_o_periodo(app, lancamentos):
    """Abril tem só o aluguel; março fica de fora."""
    resumo = services.calcular_resumo(date(2026, 4, 1), date(2026, 4, 30))

    assert resumo.receitas == Decimal("0.00")
    assert resumo.despesas == Decimal("1800.00")
    assert resumo.saldo == Decimal("-1800.00")


def test_resumo_sem_lancamentos_da_zero(app):
    resumo = services.calcular_resumo()

    assert resumo.receitas == Decimal("0.00")
    assert resumo.saldo == Decimal("0.00")


def test_totais_por_categoria_ordena_do_maior(app, lancamentos):
    totais = services.totais_por_categoria(TipoLancamento.DESPESA)

    assert [t.categoria for t in totais] == ["Moradia", "Lazer"]
    assert totais[0].total == Decimal("3600.00")


def test_percentual_soma_aproximadamente_cem(app, lancamentos):
    totais = services.totais_por_categoria(TipoLancamento.DESPESA)

    assert sum(t.percentual for t in totais) == Decimal("100.0")


def test_percentual_sem_dados_nao_divide_por_zero(app):
    assert services.totais_por_categoria(TipoLancamento.DESPESA) == []


def test_busca_filtra_por_tipo(app, lancamentos):
    receitas = services.buscar_lancamentos(tipo=TipoLancamento.RECEITA)

    assert len(receitas) == 1
    assert receitas[0].descricao == "Salário de março"


def test_busca_filtra_por_texto_sem_diferenciar_maiusculas(app, lancamentos):
    assert len(services.buscar_lancamentos(texto="aluguel")) == 2
    assert len(services.buscar_lancamentos(texto="ALUGUEL")) == 2


def test_busca_ordena_do_mais_recente(app, lancamentos):
    resultado = services.buscar_lancamentos()

    assert resultado[0].data == date(2026, 4, 10)
    assert resultado[-1].data == date(2026, 3, 5)


def test_busca_combina_filtros(app, lancamentos, categorias):
    resultado = services.buscar_lancamentos(
        inicio=date(2026, 3, 1),
        fim=date(2026, 3, 31),
        categoria_id=categorias["moradia"].id,
    )

    assert len(resultado) == 1
    assert resultado[0].data == date(2026, 3, 10)


def test_evolucao_mensal_preenche_os_doze_meses(app, lancamentos):
    evolucao = services.evolucao_mensal(2026)

    assert len(evolucao) == 12

    marco = evolucao[2]
    assert marco["receitas"] == Decimal("5000.00")
    assert marco["despesas"] == Decimal("1864.90")
    assert marco["saldo"] == Decimal("3135.10")

    janeiro = evolucao[0]
    assert janeiro["receitas"] == Decimal("0.00")
    assert janeiro["saldo"] == Decimal("0.00")
