from datetime import date

from flask import Blueprint, render_template
from flask_login import current_user, login_required

from app import services
from app.extensions import db
from app.models import TipoLancamento

bp = Blueprint("main", __name__)


@bp.get("/")
@login_required
def index():
    hoje = date.today()
    inicio_mes = hoje.replace(day=1)
    eu = current_user.id

    return render_template(
        "index.html",
        hoje=hoje,
        inicio_mes=inicio_mes,
        resumo_mes=services.calcular_resumo(eu, inicio_mes, hoje),
        resumo_total=services.calcular_resumo(eu),
        despesas_por_categoria=services.totais_por_categoria(
            eu, TipoLancamento.DESPESA, inicio_mes, hoje
        ),
        receitas_por_categoria=services.totais_por_categoria(
            eu, TipoLancamento.RECEITA, inicio_mes, hoje
        ),
        ultimos=services.buscar_lancamentos(eu)[:8],
        evolucao=services.evolucao_mensal(eu, hoje.year),
    )


@bp.get("/health")
def health():
    """Sem login: é usada por monitoramento, e não expõe dado algum."""
    try:
        db.session.execute(db.text("SELECT 1"))
    except Exception:
        return {"status": "degraded", "database": "unreachable"}, 503
    return {"status": "ok", "database": "ok"}
