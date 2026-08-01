from datetime import date
from decimal import Decimal

import pytest

from app import create_app
from app.config import TestingConfig
from app.extensions import db as _db
from app.models import Categoria, Lancamento, TipoLancamento


@pytest.fixture
def app():
    app = create_app(TestingConfig)
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    return _db


@pytest.fixture
def categorias(db):
    salario = Categoria(nome="Salário", tipo=TipoLancamento.RECEITA)
    moradia = Categoria(nome="Moradia", tipo=TipoLancamento.DESPESA)
    lazer = Categoria(nome="Lazer", tipo=TipoLancamento.DESPESA)
    db.session.add_all([salario, moradia, lazer])
    db.session.commit()
    return {"salario": salario, "moradia": moradia, "lazer": lazer}


@pytest.fixture
def lancamentos(db, categorias):
    itens = [
        Lancamento(
            descricao="Salário de março",
            valor=Decimal("5000.00"),
            data=date(2026, 3, 5),
            categoria=categorias["salario"],
        ),
        Lancamento(
            descricao="Aluguel",
            valor=Decimal("1800.00"),
            data=date(2026, 3, 10),
            categoria=categorias["moradia"],
        ),
        Lancamento(
            descricao="Cinema",
            valor=Decimal("64.90"),
            data=date(2026, 3, 15),
            categoria=categorias["lazer"],
        ),
        Lancamento(
            descricao="Aluguel",
            valor=Decimal("1800.00"),
            data=date(2026, 4, 10),
            categoria=categorias["moradia"],
        ),
    ]
    db.session.add_all(itens)
    db.session.commit()
    return itens
