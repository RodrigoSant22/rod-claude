"""Consultas e cálculos do fluxo de caixa."""

from datetime import date
from decimal import Decimal

from app import services
from app.models import TipoLancamento


def test_resumo_soma_receitas_e_despesas(app, usuario, lancamentos):
    resumo = services.calcular_resumo(usuario.id)

    assert resumo.receitas == Decimal("5000.00")
    assert resumo.despesas == Decimal("3664.90")
    assert resumo.saldo == Decimal("1335.10")


def test_resumo_respeita_o_periodo(app, usuario, lancamentos):
    """Abril tem só o aluguel; março fica de fora."""
    resumo = services.calcular_resumo(usuario.id, date(2026, 4, 1), date(2026, 4, 30))

    assert resumo.receitas == Decimal("0.00")
    assert resumo.despesas == Decimal("1800.00")
    assert resumo.saldo == Decimal("-1800.00")


def test_resumo_sem_lancamentos_da_zero(app, usuario):
    resumo = services.calcular_resumo(usuario.id)

    assert resumo.receitas == Decimal("0.00")
    assert resumo.saldo == Decimal("0.00")


def test_totais_por_categoria_ordena_do_maior(app, usuario, lancamentos):
    totais = services.totais_por_categoria(usuario.id, TipoLancamento.DESPESA)

    assert [t.categoria for t in totais] == ["Moradia", "Lazer"]
    assert totais[0].total == Decimal("3600.00")


def test_percentual_soma_aproximadamente_cem(app, usuario, lancamentos):
    totais = services.totais_por_categoria(usuario.id, TipoLancamento.DESPESA)

    assert sum(t.percentual for t in totais) == Decimal("100.0")


def test_percentual_sem_dados_nao_divide_por_zero(app, usuario):
    assert services.totais_por_categoria(usuario.id, TipoLancamento.DESPESA) == []


def test_busca_filtra_por_tipo(app, usuario, lancamentos):
    receitas = services.buscar_lancamentos(usuario.id, tipo=TipoLancamento.RECEITA)

    assert len(receitas) == 1
    assert receitas[0].descricao == "Salário de março"


def test_busca_filtra_por_texto_sem_diferenciar_maiusculas(app, usuario, lancamentos):
    assert len(services.buscar_lancamentos(usuario.id, texto="aluguel")) == 2
    assert len(services.buscar_lancamentos(usuario.id, texto="ALUGUEL")) == 2


def test_busca_ordena_do_mais_recente(app, usuario, lancamentos):
    resultado = services.buscar_lancamentos(usuario.id)

    assert resultado[0].data == date(2026, 4, 10)
    assert resultado[-1].data == date(2026, 3, 5)


def test_busca_combina_filtros(app, usuario, lancamentos, categorias):
    resultado = services.buscar_lancamentos(
        usuario.id,
        inicio=date(2026, 3, 1),
        fim=date(2026, 3, 31),
        categoria_id=categorias["moradia"].id,
    )

    assert len(resultado) == 1
    assert resultado[0].data == date(2026, 3, 10)


def test_evolucao_mensal_preenche_os_doze_meses(app, usuario, lancamentos):
    evolucao = services.evolucao_mensal(usuario.id, 2026)

    assert len(evolucao) == 12

    marco = evolucao[2]
    assert marco["receitas"] == Decimal("5000.00")
    assert marco["despesas"] == Decimal("1864.90")
    assert marco["saldo"] == Decimal("3135.10")

    janeiro = evolucao[0]
    assert janeiro["receitas"] == Decimal("0.00")
    assert janeiro["saldo"] == Decimal("0.00")


def test_categorias_do_usuario_pode_filtrar_ativas(app, db, usuario, categorias):
    categorias["lazer"].ativa = False
    db.session.commit()

    todas = services.categorias_do_usuario(usuario.id)
    ativas = services.categorias_do_usuario(usuario.id, apenas_ativas=True)

    assert len(todas) == 3
    assert len(ativas) == 2
