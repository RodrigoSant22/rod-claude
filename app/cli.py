"""Comandos de linha de comando registrados no app."""

import click
from flask import Flask

from app.extensions import db
from app.forms import SENHA_MINIMA
from app.models import Categoria, Lancamento, TipoLancamento, Usuario

CATEGORIAS_PADRAO = [
    ("Salário", TipoLancamento.RECEITA),
    ("Freelance", TipoLancamento.RECEITA),
    ("Investimentos", TipoLancamento.RECEITA),
    ("Outras receitas", TipoLancamento.RECEITA),
    ("Moradia", TipoLancamento.DESPESA),
    ("Alimentação", TipoLancamento.DESPESA),
    ("Transporte", TipoLancamento.DESPESA),
    ("Saúde", TipoLancamento.DESPESA),
    ("Educação", TipoLancamento.DESPESA),
    ("Lazer", TipoLancamento.DESPESA),
    ("Outras despesas", TipoLancamento.DESPESA),
]


def _resolver_usuario(email: str | None) -> Usuario | None:
    """Usa o e-mail informado, ou o único usuário existente."""
    if email:
        return Usuario.query.filter_by(email=Usuario.normalizar_email(email)).first()

    usuarios = Usuario.query.limit(2).all()
    return usuarios[0] if len(usuarios) == 1 else None


def _adotar_orfaos(usuario: Usuario) -> int:
    """Atribui ao usuário os registros criados antes de existir login.

    Só faz sentido na primeira conta: a partir da segunda, não há como
    adivinhar de quem era o dado.
    """
    total = 0
    for modelo in (Categoria, Lancamento):
        orfaos = modelo.query.filter_by(usuario_id=None).all()
        for registro in orfaos:
            registro.usuario_id = usuario.id
        total += len(orfaos)

    if total:
        db.session.commit()
    return total


def registrar(app: Flask) -> None:
    @app.cli.command("init-db")
    def init_db():
        """Cria as tabelas (atalho para quem não vai usar migrações)."""
        db.create_all()
        click.echo("Tabelas criadas.")

    @app.cli.command("criar-usuario")
    @click.option("--email", prompt="E-mail", help="E-mail de acesso.")
    @click.option("--nome", prompt="Nome", help="Nome exibido no topo.")
    @click.option(
        "--senha",
        prompt="Senha",
        hide_input=True,
        confirmation_prompt="Repita a senha",
        help="Senha de acesso.",
    )
    def criar_usuario(email: str, nome: str, senha: str):
        """Cria uma conta de acesso. Não há cadastro pela web, de propósito."""
        email = Usuario.normalizar_email(email)

        if len(senha) < SENHA_MINIMA:
            raise click.ClickException(f"A senha precisa de ao menos {SENHA_MINIMA} caracteres.")

        if Usuario.query.filter_by(email=email).first():
            raise click.ClickException(f"Já existe um usuário com o e-mail {email}.")

        primeiro = Usuario.query.count() == 0

        usuario = Usuario(nome=nome.strip(), email=email)
        usuario.definir_senha(senha)
        db.session.add(usuario)
        db.session.commit()

        click.echo(f"Usuário {email} criado.")

        if primeiro:
            adotados = _adotar_orfaos(usuario)
            if adotados:
                click.echo(f"{adotados} registro(s) sem dono atribuído(s) a esta conta.")

    @app.cli.command("limpar-tentativas")
    @click.option("--dias", default=30, show_default=True, help="Idade a partir da qual descartar.")
    def limpar_tentativas(dias: int):
        """Descarta registros antigos de tentativas de acesso."""
        from app import seguranca

        removidas = seguranca.limpar_antigas(dias)
        click.echo(f"{removidas} registro(s) removido(s).")

    @app.cli.command("seed")
    @click.option("--email", default=None, help="Conta que receberá as categorias.")
    def seed(email: str | None):
        """Cadastra as categorias padrão, pulando as que já existem."""
        usuario = _resolver_usuario(email)
        if usuario is None:
            raise click.ClickException(
                "Informe --email. Crie uma conta antes com: flask criar-usuario"
            )

        criadas = 0
        for nome, tipo in CATEGORIAS_PADRAO:
            existe = Categoria.query.filter_by(
                nome=nome, tipo=tipo, usuario_id=usuario.id
            ).first()
            if not existe:
                db.session.add(Categoria(nome=nome, tipo=tipo, usuario_id=usuario.id))
                criadas += 1

        db.session.commit()
        click.echo(f"{criadas} categoria(s) criada(s) para {usuario.email}.")
