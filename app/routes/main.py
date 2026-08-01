from datetime import date

from flask import Blueprint, render_template

from app import services
from app.extensions import db
from app.models import TipoLancamento

bp = Blueprint("main", __name__)


@bp.get("/")
def index():
    hoje = date.today()
    inicio_mes = hoje.replace(day=1)

    return render_template(
        "index.html",
        hoje=hoje,
        inicio_mes=inicio_mes,
        resumo_mes=services.calcular_resumo(inicio_mes, hoje),
        resumo_total=services.calcular_resumo(),
        despesas_por_categoria=services.totais_por_categoria(
            TipoLancamento.DESPESA, inicio_mes, hoje
        ),
        receitas_por_categoria=services.totais_por_categoria(
            TipoLancamento.RECEITA, inicio_mes, hoje
        ),
        ultimos=services.buscar_lancamentos()[:8],
        evolucao=services.evolucao_mensal(hoje.year),
    )


@bp.get("/health")
def health():
    """Checagem de saúde: responde 503 se o banco não estiver acessível."""
    try:
        db.session.execute(db.text("SELECT 1"))
    except Exception:
        return {"status": "degraded", "database": "unreachable"}, 503
    return {"status": "ok", "database": "ok"}
