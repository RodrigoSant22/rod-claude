"""Fixtures compartilhadas pela suíte.

Cada teste recebe um app novo com SQLite em memória, criado e destruído em
milissegundos — nenhum teste enxerga o resíduo do anterior.
"""

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
    """App de teste com banco em memória, descartado ao fim de cada teste.

    O `yield` dentro do `with` entrega o app ao teste e retoma depois para
    limpar — mesmo mecanismo de um gerenciador de contexto.
    """
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
    """A sessão do SQLAlchemy, já dentro do contexto do app de teste."""
    return _db


def _criar_usuario(db, nome: str, email: str) -> Usuario:
    """Cria uma conta com a senha padrão da suíte."""
    usuario = Usuario(nome=nome, email=email)
    usuario.definir_senha(SENHA)
    db.session.add(usuario)
    db.session.commit()
    return usuario


@pytest.fixture
def usuario(db):
    """Conta principal dos testes."""
    return _criar_usuario(db, "Rodrigo", "rodrigo@exemplo.com")


@pytest.fixture
def outro_usuario(db):
    """Segunda conta, usada para provar que um não enxerga o outro."""
    return _criar_usuario(db, "Alex", "alex@exemplo.com")


def _logar(client, email: str) -> None:
    """Faz login no cliente, deixando o cookie de sessão pronto."""
    resposta = client.post(
        "/login", data={"email": email, "senha": SENHA}, follow_redirects=True
    )
    assert resposta.status_code == 200


@pytest.fixture
def logado(app, usuario):
    """Cliente já autenticado como a conta principal."""
    cliente = app.test_client()
    _logar(cliente, usuario.email)
    return cliente


@pytest.fixture
def logado_outro(app, outro_usuario):
    """Cliente autenticado como a segunda conta."""
    cliente = app.test_client()
    _logar(cliente, outro_usuario.email)
    return cliente


@pytest.fixture
def categorias(db, usuario):
    """Três categorias da conta principal, por nome."""
    salario = Categoria(nome="Salário", tipo=TipoLancamento.RECEITA, usuario_id=usuario.id)
    moradia = Categoria(nome="Moradia", tipo=TipoLancamento.DESPESA, usuario_id=usuario.id)
    lazer = Categoria(nome="Lazer", tipo=TipoLancamento.DESPESA, usuario_id=usuario.id)
    db.session.add_all([salario, moradia, lazer])
    db.session.commit()
    return {"salario": salario, "moradia": moradia, "lazer": lazer}


@pytest.fixture
def lancamentos(db, usuario, categorias):
    """Quatro lançamentos em março e abril de 2026, da conta principal."""
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
