"""Comandos de linha de comando registrados no app."""

import click
from flask import Flask

from app.extensions import db
from app.models import Categoria, TipoLancamento

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


def registrar(app: Flask) -> None:
    @app.cli.command("init-db")
    def init_db():
        """Cria as tabelas (atalho para quem não vai usar migrações)."""
        db.create_all()
        click.echo("Tabelas criadas.")

    @app.cli.command("seed")
    def seed():
        """Cadastra as categorias padrão, pulando as que já existem."""
        criadas = 0
        for nome, tipo in CATEGORIAS_PADRAO:
            existe = Categoria.query.filter_by(nome=nome, tipo=tipo).first()
            if not existe:
                db.session.add(Categoria(nome=nome, tipo=tipo))
                criadas += 1

        db.session.commit()
        click.echo(f"{criadas} categoria(s) criada(s).")
