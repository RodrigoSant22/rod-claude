from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.extensions import db
from app.forms import AlterarSenhaForm, LoginForm
from app.models import Usuario

bp = Blueprint("auth", __name__)


def _destino_seguro(destino: str | None) -> str:
    """Só aceita redirecionamento para dentro da própria aplicação.

    Sem isso, `?next=https://site-malicioso` transformaria o login em um
    redirecionador aberto, útil para phishing.
    """
    padrao = url_for("main.index")
    if not destino:
        return padrao

    partes = urlparse(destino)
    if partes.scheme or partes.netloc or not destino.startswith("/"):
        return padrao
    return destino


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    form = LoginForm()
    if form.validate_on_submit():
        usuario = Usuario.query.filter_by(
            email=Usuario.normalizar_email(form.email.data)
        ).first()

        # Mensagem única para e-mail inexistente, senha errada e conta
        # desativada: revelar qual dos três facilitaria descobrir e-mails
        # válidos.
        if usuario and usuario.ativo and usuario.conferir_senha(form.senha.data):
            login_user(usuario, remember=form.lembrar.data)
            return redirect(_destino_seguro(request.args.get("next")))

        flash("E-mail ou senha incorretos.", "erro")

    return render_template("auth/login.html", form=form)


@bp.post("/logout")
@login_required
def logout():
    logout_user()
    flash("Sessão encerrada.", "sucesso")
    return redirect(url_for("auth.login"))


@bp.route("/conta/senha", methods=["GET", "POST"])
@login_required
def alterar_senha():
    form = AlterarSenhaForm()

    if form.validate_on_submit():
        if not current_user.conferir_senha(form.senha_atual.data):
            flash("Senha atual incorreta.", "erro")
        else:
            current_user.definir_senha(form.nova_senha.data)
            db.session.commit()
            flash("Senha alterada.", "sucesso")
            return redirect(url_for("main.index"))

    return render_template("auth/alterar_senha.html", form=form)
