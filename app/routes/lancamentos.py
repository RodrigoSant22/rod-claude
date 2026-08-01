from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app import services
from app.extensions import db
from app.forms import LancamentoForm
from app.models import Categoria, Lancamento, TipoLancamento

bp = Blueprint("lancamentos", __name__, url_prefix="/lancamentos")


def _data(nome: str) -> date | None:
    valor = request.args.get(nome, "").strip()
    try:
        return date.fromisoformat(valor) if valor else None
    except ValueError:
        return None


def _int(nome: str) -> int | None:
    valor = request.args.get(nome, "").strip()
    return int(valor) if valor.isdigit() else None


def _tipo() -> TipoLancamento | None:
    valor = request.args.get("tipo", "").strip()
    return TipoLancamento(valor) if valor in TipoLancamento._value2member_map_ else None


def _filtros() -> dict:
    return {
        "inicio": _data("inicio"),
        "fim": _data("fim"),
        "tipo": _tipo(),
        "categoria_id": _int("categoria_id"),
        "texto": request.args.get("texto", "").strip() or None,
    }


def _categorias_ativas() -> list[Categoria]:
    return (
        Categoria.query.filter_by(ativa=True).order_by(Categoria.tipo, Categoria.nome).all()
    )


@bp.get("/")
def listar():
    filtros = _filtros()
    contexto = {
        "lancamentos": services.buscar_lancamentos(**filtros),
        "resumo": services.calcular_resumo(filtros["inicio"], filtros["fim"]),
        "categorias": _categorias_ativas(),
        "filtros": filtros,
        "tipos": list(TipoLancamento),
    }

    # HTMX pede só a tabela; o navegador sem JS recebe a página inteira.
    if request.headers.get("HX-Request"):
        return render_template("lancamentos/_tabela.html", **contexto)
    return render_template("lancamentos/listar.html", **contexto)


@bp.route("/novo", methods=["GET", "POST"])
def criar():
    form = LancamentoForm(data={"data": date.today()})
    form.carregar_categorias(_categorias_ativas())

    if not form.categoria_id.choices:
        flash("Cadastre ao menos uma categoria antes de lançar.", "aviso")
        return redirect(url_for("categorias.criar"))

    if form.validate_on_submit():
        lancamento = Lancamento(
            descricao=form.descricao.data,
            valor=form.valor.data,
            data=form.data.data,
            categoria_id=form.categoria_id.data,
            observacao=form.observacao.data or None,
        )
        db.session.add(lancamento)
        db.session.commit()
        flash("Lançamento registrado.", "sucesso")
        return redirect(url_for("lancamentos.listar"))

    return render_template("lancamentos/form.html", form=form, lancamento=None)


@bp.route("/<int:lancamento_id>/editar", methods=["GET", "POST"])
def editar(lancamento_id: int):
    lancamento = db.get_or_404(Lancamento, lancamento_id)
    form = LancamentoForm(obj=lancamento)
    form.carregar_categorias(_categorias_ativas())

    if form.validate_on_submit():
        form.populate_obj(lancamento)
        db.session.commit()
        flash("Lançamento atualizado.", "sucesso")
        return redirect(url_for("lancamentos.listar"))

    return render_template("lancamentos/form.html", form=form, lancamento=lancamento)


@bp.post("/<int:lancamento_id>/excluir")
def excluir(lancamento_id: int):
    lancamento = db.get_or_404(Lancamento, lancamento_id)
    db.session.delete(lancamento)
    db.session.commit()

    if request.headers.get("HX-Request"):
        filtros = _filtros()
        return render_template(
            "lancamentos/_tabela.html",
            lancamentos=services.buscar_lancamentos(**filtros),
            resumo=services.calcular_resumo(filtros["inicio"], filtros["fim"]),
            filtros=filtros,
        )

    flash("Lançamento excluído.", "sucesso")
    return redirect(url_for("lancamentos.listar"))
