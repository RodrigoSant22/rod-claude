"""CRUD de lançamentos, com filtros e exportação.

Todas as rotas exigem login (via `before_request`) e enxergam apenas os dados
da conta autenticada.
"""

from datetime import date

from flask import (
    Blueprint,
    Response,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from app import exportacao, services
from app.extensions import db
from app.forms import LancamentoForm
from app.models import Categoria, Lancamento, TipoLancamento

bp = Blueprint("lancamentos", __name__, url_prefix="/lancamentos")

_EXPORTADORES = {
    "csv": (exportacao.gerar_csv, "text/csv; charset=utf-8"),
    "xlsx": (
        exportacao.gerar_xlsx,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ),
}


@bp.before_request
@login_required
def exigir_login():
    """Protege todas as rotas do blueprint, sem repetir o decorator em cada uma."""


def _data(nome: str) -> date | None:
    """Lê uma data da query string. Valor ausente ou inválido vira None.

    Engolir o erro é proposital: uma data digitada errada na URL deve apenas
    ignorar o filtro, não devolver 400 ao visitante.
    """
    valor = request.args.get(nome, "").strip()
    try:
        return date.fromisoformat(valor) if valor else None
    except ValueError:
        return None


def _int(nome: str) -> int | None:
    """Lê um inteiro da query string, ou None se não for um número."""
    valor = request.args.get(nome, "").strip()
    return int(valor) if valor.isdigit() else None


def _tipo() -> TipoLancamento | None:
    """Lê o tipo da query string, aceitando apenas os valores do enum."""
    valor = request.args.get("tipo", "").strip()
    return TipoLancamento(valor) if valor in TipoLancamento._value2member_map_ else None


def _filtros() -> dict:
    """Reúne os filtros da query string.

    As chaves batem com os parâmetros de `services.buscar_lancamentos`, o que
    permite repassar com `**filtros`.
    """
    return {
        "inicio": _data("inicio"),
        "fim": _data("fim"),
        "tipo": _tipo(),
        "categoria_id": _int("categoria_id"),
        "texto": request.args.get("texto", "").strip() or None,
    }


def _meu_lancamento(lancamento_id: int) -> Lancamento:
    """404 para lançamento de outra conta — nunca 403.

    Responder 403 confirmaria que aquele id existe; 404 não revela nada.
    """
    return db.one_or_404(
        db.select(Lancamento).filter_by(id=lancamento_id, usuario_id=current_user.id)
    )


def _links_exportacao(filtros: dict) -> dict[str, str]:
    """URLs de exportação carregando os filtros ativos.

    Ficam no fragmento da tabela, e não na página: como o HTMX troca só o
    fragmento ao filtrar, links montados fora dele guardariam os filtros
    antigos.
    """
    argumentos = {
        chave: (valor.isoformat() if hasattr(valor, "isoformat") else valor)
        for chave, valor in filtros.items()
        if valor is not None
    }
    return {
        f"url_{formato}": url_for("lancamentos.exportar", formato=formato, **argumentos)
        for formato in _EXPORTADORES
    }


def _minhas_categorias_ativas() -> list[Categoria]:
    """Categorias ativas do usuário logado, para preencher os formulários."""
    return services.categorias_do_usuario(current_user.id, apenas_ativas=True)


@bp.get("/")
def listar():
    """Lista os lançamentos filtrados, com o resumo do período.

    Responde a página inteira, ou só o fragmento da tabela quando o pedido vem
    do HTMX — o que é identificado pelo cabeçalho `HX-Request`.
    """
    filtros = _filtros()
    contexto = {
        "lancamentos": services.buscar_lancamentos(current_user.id, **filtros),
        "resumo": services.calcular_resumo(current_user.id, filtros["inicio"], filtros["fim"]),
        "categorias": _minhas_categorias_ativas(),
        "filtros": filtros,
        "tipos": list(TipoLancamento),
        **_links_exportacao(filtros),
    }

    # HTMX pede só a tabela; o navegador sem JS recebe a página inteira.
    if request.headers.get("HX-Request"):
        return render_template("lancamentos/_tabela.html", **contexto)
    return render_template("lancamentos/listar.html", **contexto)


@bp.route("/novo", methods=["GET", "POST"])
def criar():
    """Formulário de novo lançamento, e sua gravação.

    Sem nenhuma categoria cadastrada não há o que escolher, então a rota
    desvia para o cadastro de categorias em vez de mostrar um select vazio.
    """
    form = LancamentoForm(data={"data": date.today()})
    categorias = _minhas_categorias_ativas()
    form.carregar_categorias(categorias)

    if not form.categoria_id.choices:
        flash("Cadastre ao menos uma categoria antes de lançar.", "aviso")
        return redirect(url_for("categorias.criar"))

    if form.validate_on_submit():
        db.session.add(
            Lancamento(
                descricao=form.descricao.data,
                valor=form.valor.data,
                data=form.data.data,
                categoria_id=form.categoria_id.data,
                observacao=form.observacao.data or None,
                usuario_id=current_user.id,
            )
        )
        db.session.commit()
        flash("Lançamento registrado.", "sucesso")
        return redirect(url_for("lancamentos.listar"))

    return render_template("lancamentos/form.html", form=form, lancamento=None)


@bp.route("/<int:lancamento_id>/editar", methods=["GET", "POST"])
def editar(lancamento_id: int):
    """Edição de um lançamento da própria conta.

    `populate_obj` copia os campos do formulário para o objeto; como ele já
    está na sessão do SQLAlchemy, basta commitar.
    """
    lancamento = _meu_lancamento(lancamento_id)
    form = LancamentoForm(obj=lancamento)
    form.carregar_categorias(_minhas_categorias_ativas())

    if form.validate_on_submit():
        form.populate_obj(lancamento)
        db.session.commit()
        flash("Lançamento atualizado.", "sucesso")
        return redirect(url_for("lancamentos.listar"))

    return render_template("lancamentos/form.html", form=form, lancamento=lancamento)


@bp.get("/exportar.<formato>")
def exportar(formato: str):
    """Baixa os lançamentos filtrados em CSV ou XLSX.

    O `Content-Disposition: attachment` é o que faz o navegador salvar o
    arquivo em vez de tentar exibi-lo.
    """
    if formato not in _EXPORTADORES:
        abort(404)

    gerar, tipo_mime = _EXPORTADORES[formato]
    filtros = _filtros()
    conteudo = gerar(services.buscar_lancamentos(current_user.id, **filtros))

    return Response(
        conteudo,
        mimetype=tipo_mime,
        headers={
            "Content-Disposition": (
                "attachment; filename="
                + exportacao.nome_arquivo(formato, filtros["inicio"], filtros["fim"])
            )
        },
    )


@bp.post("/<int:lancamento_id>/excluir")
def excluir(lancamento_id: int):
    """Exclui um lançamento da própria conta.

    Ao HTMX devolve a tabela já atualizada; ao navegador comum, redireciona
    com mensagem.
    """
    lancamento = _meu_lancamento(lancamento_id)
    db.session.delete(lancamento)
    db.session.commit()

    if request.headers.get("HX-Request"):
        filtros = _filtros()
        return render_template(
            "lancamentos/_tabela.html",
            lancamentos=services.buscar_lancamentos(current_user.id, **filtros),
            resumo=services.calcular_resumo(
                current_user.id, filtros["inicio"], filtros["fim"]
            ),
            filtros=filtros,
            **_links_exportacao(filtros),
        )

    flash("Lançamento excluído.", "sucesso")
    return redirect(url_for("lancamentos.listar"))
