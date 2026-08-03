from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Categoria, Lancamento, TipoLancamento


def test_valor_e_decimal_nao_float(db, categorias):
    lancamento = Lancamento(
        descricao="Teste",
        valor=Decimal("0.10"),
        data=date(2026, 3, 1),
        categoria=categorias["moradia"],
    )
    db.session.add(lancamento)
    db.session.commit()

    recarregado = db.session.get(Lancamento, lancamento.id)
    assert isinstance(recarregado.valor, Decimal)
    assert not isinstance(recarregado.valor, float)


def test_soma_decimal_nao_acumula_erro(db, categorias):
    """0.1 + 0.2 em float dá 0.30000000000000004; com Decimal dá exato."""
    for centavos in ("0.10", "0.20"):
        db.session.add(
            Lancamento(
                descricao=f"Item {centavos}",
                valor=Decimal(centavos),
                data=date(2026, 3, 1),
                categoria=categorias["moradia"],
            )
        )
    db.session.commit()

    total = sum(item.valor for item in Lancamento.query.all())
    assert total == Decimal("0.30")


def test_tipo_do_lancamento_vem_da_categoria(db, categorias):
    lancamento = Lancamento(
        descricao="Salário",
        valor=Decimal("100.00"),
        data=date(2026, 3, 1),
        categoria=categorias["salario"],
    )
    db.session.add(lancamento)
    db.session.commit()

    assert lancamento.tipo is TipoLancamento.RECEITA


def test_valor_com_sinal_inverte_despesa(db, categorias):
    receita = Lancamento(
        descricao="Entrada",
        valor=Decimal("100.00"),
        data=date(2026, 3, 1),
        categoria=categorias["salario"],
    )
    despesa = Lancamento(
        descricao="Saída",
        valor=Decimal("100.00"),
        data=date(2026, 3, 1),
        categoria=categorias["moradia"],
    )
    db.session.add_all([receita, despesa])
    db.session.commit()

    assert receita.valor_com_sinal == Decimal("100.00")
    assert despesa.valor_com_sinal == Decimal("-100.00")


def test_banco_rejeita_valor_zero_ou_negativo(db, categorias):
    db.session.add(
        Lancamento(
            descricao="Inválido",
            valor=Decimal("-5.00"),
            data=date(2026, 3, 1),
            categoria=categorias["moradia"],
        )
    )
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_categoria_nao_repete_nome_no_mesmo_tipo(db, usuario, categorias):
    """A unicidade é por conta: mesmo dono, mesmo nome, mesmo tipo colide."""
    db.session.add(
        Categoria(nome="Moradia", tipo=TipoLancamento.DESPESA, usuario_id=usuario.id)
    )
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_mesmo_nome_em_tipos_diferentes_e_permitido(db, usuario, categorias):
    db.session.add(
        Categoria(nome="Moradia", tipo=TipoLancamento.RECEITA, usuario_id=usuario.id)
    )
    db.session.commit()
    assert Categoria.query.filter_by(nome="Moradia").count() == 2


def test_em_uso_detecta_lancamentos(db, categorias, lancamentos):
    assert categorias["moradia"].em_uso is True
    assert Categoria(nome="Nova", tipo=TipoLancamento.DESPESA).em_uso is False
