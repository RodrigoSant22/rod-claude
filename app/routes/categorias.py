"""CRUD de categorias.

Categoria com histórico nunca é apagada — apenas desativada, para não levar
os lançamentos junto.
"""

from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from app import services
from app.extensions import db
from app.forms import CategoriaForm
from app.models import Categoria

bp = Blueprint("categorias", __name__, url_prefix="/categorias")


@bp.before_request
@login_required
def exigir_login():
    """Protege todas as rotas do blueprint, sem repetir o decorator em cada uma."""


def _minha_categoria(categoria_id: int) -> Categoria:
    """404 para categoria de outra conta — ver a nota em lancamentos._meu_lancamento."""
    return db.one_or_404(
        db.select(Categoria).filter_by(id=categoria_id, usuario_id=current_user.id)
    )


@bp.get("/")
def listar():
    """Lista as categorias da conta, ativas e inativas."""
    return render_template(
        "categorias/listar.html", categorias=services.categorias_do_usuario(current_user.id)
    )


@bp.route("/nova", methods=["GET", "POST"])
def criar():
    """Formulário de nova categoria, e sua gravação."""
    form = CategoriaForm()

    if form.validate_on_submit():
        if _ja_existe(form.nome.data, form.tipo.data):
            flash("Já existe uma categoria com esse nome e tipo.", "erro")
        else:
            db.session.add(
                Categoria(
                    nome=form.nome.data,
                    tipo=form.tipo.data,
                    ativa=form.ativa.data,
                    usuario_id=current_user.id,
                )
            )
            db.session.commit()
            flash("Categoria criada.", "sucesso")
            return redirect(url_for("categorias.listar"))

    return render_template("categorias/form.html", form=form, categoria=None)


@bp.route("/<int:categoria_id>/editar", methods=["GET", "POST"])
def editar(categoria_id: int):
    """Edição de uma categoria da própria conta."""
    categoria = _minha_categoria(categoria_id)
    form = CategoriaForm(obj=categoria)

    if form.validate_on_submit():
        if _ja_existe(form.nome.data, form.tipo.data, exceto=categoria.id):
            flash("Já existe uma categoria com esse nome e tipo.", "erro")
        else:
            form.populate_obj(categoria)
            db.session.commit()
            flash("Categoria atualizada.", "sucesso")
            return redirect(url_for("categorias.listar"))

    return render_template("categorias/form.html", form=form, categoria=categoria)


@bp.post("/<int:categoria_id>/excluir")
def excluir(categoria_id: int):
    """Exclui a categoria, ou apenas a desativa se já houver lançamentos."""
    categoria = _minha_categoria(categoria_id)

    # Excluir apagaria o histórico junto. Categoria em uso só é desativada.
    if categoria.em_uso:
        categoria.ativa = False
        db.session.commit()
        flash(f'"{categoria.nome}" tem lançamentos e foi desativada em vez de excluída.', "aviso")
    else:
        db.session.delete(categoria)
        db.session.commit()
        flash("Categoria excluída.", "sucesso")

    return redirect(url_for("categorias.listar"))


def _ja_existe(nome: str, tipo: str, exceto: int | None = None) -> bool:
    """Duplicidade é checada dentro da conta: nomes iguais entre usuários são normais."""
    query = Categoria.query.filter(
        Categoria.nome.ilike(nome),
        Categoria.tipo == tipo,
        Categoria.usuario_id == current_user.id,
    )
    if exceto:
        query = query.filter(Categoria.id != exceto)
    return db.session.query(query.exists()).scalar()
