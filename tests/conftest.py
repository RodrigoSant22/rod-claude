from datetime import date
from decimal import Decimal

import pytest

from app import create_app
from app.config import TestingConfig
from app.extensions import db as _db
from app.models import Categoria, Lancamento, TipoLancamento, Usuario

SENHA = "senha-de-teste"


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
    """Cliente sem sessão — para verificar que as rotas exigem login."""
    return app.test_client()


@pytest.fixture
def db(app):
    return _db


def _criar_usuario(db, nome: str, email: str) -> Usuario:
    usuario = Usuario(nome=nome, email=email)
    usuario.definir_senha(SENHA)
    db.session.add(usuario)
    db.session.commit()
    return usuario


@pytest.fixture
def usuario(db):
    return _criar_usuario(db, "Rodrigo", "rodrigo@exemplo.com")


@pytest.fixture
def outro_usuario(db):
    """Segunda conta, usada para provar que um não enxerga o outro."""
    return _criar_usuario(db, "Alex", "alex@exemplo.com")


def _logar(client, email: str) -> None:
    resposta = client.post(
        "/login", data={"email": email, "senha": SENHA}, follow_redirects=True
    )
    assert resposta.status_code == 200


@pytest.fixture
def logado(app, usuario):
    cliente = app.test_client()
    _logar(cliente, usuario.email)
    return cliente


@pytest.fixture
def logado_outro(app, outro_usuario):
    cliente = app.test_client()
    _logar(cliente, outro_usuario.email)
    return cliente


@pytest.fixture
def categorias(db, usuario):
    salario = Categoria(nome="Salário", tipo=TipoLancamento.RECEITA, usuario_id=usuario.id)
    moradia = Categoria(nome="Moradia", tipo=TipoLancamento.DESPESA, usuario_id=usuario.id)
    lazer = Categoria(nome="Lazer", tipo=TipoLancamento.DESPESA, usuario_id=usuario.id)
    db.session.add_all([salario, moradia, lazer])
    db.session.commit()
    return {"salario": salario, "moradia": moradia, "lazer": lazer}


@pytest.fixture
def lancamentos(db, usuario, categorias):
    itens = [
        Lancamento(
            descricao="Salário de março",
            valor=Decimal("5000.00"),
            data=date(2026, 3, 5),
            categoria=categorias["salario"],
            usuario_id=usuario.id,
        ),
        Lancamento(
            descricao="Aluguel",
            valor=Decimal("1800.00"),
            data=date(2026, 3, 10),
            categoria=categorias["moradia"],
            usuario_id=usuario.id,
        ),
        Lancamento(
            descricao="Cinema",
            valor=Decimal("64.90"),
            data=date(2026, 3, 15),
            categoria=categorias["lazer"],
            usuario_id=usuario.id,
        ),
        Lancamento(
            descricao="Aluguel",
            valor=Decimal("1800.00"),
            data=date(2026, 4, 10),
            categoria=categorias["moradia"],
            usuario_id=usuario.id,
        ),
    ]
    db.session.add_all(itens)
    db.session.commit()
    return itens


@pytest.fixture
def dados_do_outro(db, outro_usuario):
    """Categoria e lançamento pertencentes à segunda conta."""
    categoria = Categoria(
        nome="Viagem", tipo=TipoLancamento.DESPESA, usuario_id=outro_usuario.id
    )
    db.session.add(categoria)
    db.session.commit()

    lancamento = Lancamento(
        descricao="Passagem aérea secreta",
        valor=Decimal("2500.00"),
        data=date(2026, 3, 20),
        categoria=categoria,
        usuario_id=outro_usuario.id,
    )
    db.session.add(lancamento)
    db.session.commit()

    return {"categoria": categoria, "lancamento": lancamento}
