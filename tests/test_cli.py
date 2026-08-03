from datetime import date
from decimal import Decimal

from app.models import Categoria, Lancamento, TipoLancamento, Usuario

CRIAR = ["criar-usuario", "--email", "novo@exemplo.com", "--nome", "Novo"]


def test_criar_usuario(app, db):
    runner = app.test_cli_runner()

    resultado = runner.invoke(args=[*CRIAR, "--senha", "senha-bem-longa"])

    assert "criado" in resultado.output
    criado = Usuario.query.filter_by(email="novo@exemplo.com").one()
    assert criado.conferir_senha("senha-bem-longa")


def test_criar_usuario_recusa_senha_curta(app, db):
    runner = app.test_cli_runner()

    resultado = runner.invoke(args=[*CRIAR, "--senha", "curta"])

    assert "ao menos 8 caracteres" in resultado.output
    assert Usuario.query.count() == 0


def test_criar_usuario_recusa_email_repetido(app, db, usuario):
    runner = app.test_cli_runner()

    resultado = runner.invoke(
        args=["criar-usuario", "--email", usuario.email, "--nome", "X", "--senha", "outra-senha"]
    )

    assert "Já existe" in resultado.output
    assert Usuario.query.count() == 1


def test_email_e_normalizado_ao_criar(app, db):
    runner = app.test_cli_runner()

    runner.invoke(
        args=[
            "criar-usuario",
            "--email",
            "  MAIUSCULO@Exemplo.COM ",
            "--nome",
            "Teste",
            "--senha",
            "senha-bem-longa",
        ]
    )

    assert Usuario.query.filter_by(email="maiusculo@exemplo.com").count() == 1


def test_primeira_conta_adota_registros_sem_dono(app, db):
    """Dados criados antes do login existir precisam de um dono."""
    categoria = Categoria(nome="Antiga", tipo=TipoLancamento.DESPESA, usuario_id=None)
    db.session.add(categoria)
    db.session.commit()
    db.session.add(
        Lancamento(
            descricao="Lançamento antigo",
            valor=Decimal("100.00"),
            data=date(2026, 1, 1),
            categoria=categoria,
            usuario_id=None,
        )
    )
    db.session.commit()

    runner = app.test_cli_runner()
    resultado = runner.invoke(args=[*CRIAR, "--senha", "senha-bem-longa"])

    assert "2 registro(s) sem dono" in resultado.output

    dono = Usuario.query.filter_by(email="novo@exemplo.com").one()
    assert Categoria.query.filter_by(usuario_id=None).count() == 0
    assert Lancamento.query.filter_by(usuario_id=None).count() == 0
    assert db.session.get(Categoria, categoria.id).usuario_id == dono.id


def test_segunda_conta_nao_adota_nada(app, db, usuario):
    """Só a primeira conta adota órfãos: depois não há como saber de quem é."""
    db.session.add(Categoria(nome="Sem dono", tipo=TipoLancamento.DESPESA, usuario_id=None))
    db.session.commit()

    runner = app.test_cli_runner()
    resultado = runner.invoke(args=[*CRIAR, "--senha", "senha-bem-longa"])

    assert "sem dono" not in resultado.output
    assert Categoria.query.filter_by(usuario_id=None).count() == 1
