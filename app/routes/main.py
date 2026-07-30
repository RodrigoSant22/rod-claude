from flask import Blueprint, render_template

from app.extensions import db

bp = Blueprint("main", __name__)


@bp.get("/")
def index():
    return render_template("index.html")


@bp.get("/health")
def health():
    """Checagem de saúde: responde 503 se o banco não estiver acessível."""
    try:
        db.session.execute(db.text("SELECT 1"))
    except Exception:
        return {"status": "degraded", "database": "unreachable"}, 503
    return {"status": "ok", "database": "ok"}
