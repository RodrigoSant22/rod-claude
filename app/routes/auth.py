"""Autenticação: login, logout e os dois caminhos de troca de senha.

Este blueprint não usa `before_request`: quase tudo aqui precisa ser acessível
por quem ainda não entrou. As rotas que exigem sessão levam `@login_required`
individualmente.
"""

from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app import mailer, seguranca, tokens
from app.extensions import db
from app.forms import (
    AlterarSenhaForm,
    EsqueciSenhaForm,
    LoginForm,
    RedefinirSenhaForm,
)
from app.models import Usuario

bp = Blueprint("auth", __name__)

# Mesma resposta para e-mail inexistente, senha errada e conta desativada:
# distinguir os casos revelaria quais endereços têm conta.
CREDENCIAIS_INVALIDAS = "E-mail ou senha incorretos."

# Idem no "esqueci a senha": a mensagem não confirma se o e-mail existe.
RESET_SOLICITADO = (
    "Se houver uma conta com esse e-mail, enviamos as instruções para redefinir a senha."
)


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


def _mensagem_bloqueio(minutos: int) -> str:
    """Texto do bloqueio por excesso de tentativas, no singular ou plural."""
    unidade = "minuto" if minutos == 1 else "minutos"
    return f"Muitas tentativas. Tente novamente em {minutos} {unidade}."


@bp.route("/login", methods=["GET", "POST"])
def login():
    """Exibe o formulário e processa a entrada.

    A ordem importa: o freio de força bruta é consultado **antes** de conferir
    a senha, senão o bloqueio não conteria nada.
    """
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    form = LoginForm()
    if form.validate_on_submit():
        email = Usuario.normalizar_email(form.email.data)

        bloqueio = seguranca.verificar(seguranca.LOGIN, email)
        if bloqueio:
            flash(_mensagem_bloqueio(bloqueio.minutos_restantes), "erro")
            return render_template("auth/login.html", form=form)

        usuario = Usuario.query.filter_by(email=email).first()

        if usuario and usuario.ativo and usuario.conferir_senha(form.senha.data):
            seguranca.limpar_apos_sucesso(seguranca.LOGIN, email)
            login_user(usuario, remember=form.lembrar.data)
            return redirect(_destino_seguro(request.args.get("next")))

        seguranca.registrar(seguranca.LOGIN, email, sucesso=False)
        flash(CREDENCIAIS_INVALIDAS, "erro")

    return render_template("auth/login.html", form=form)


@bp.post("/logout")
@login_required
def logout():
    """Encerra a sessão.

    Só POST, e com token CSRF: um GET permitiria deslogar alguém com um
    simples link ou imagem escondida numa página de terceiros.
    """
    logout_user()
    flash("Sessão encerrada.", "sucesso")
    return redirect(url_for("auth.login"))


@bp.route("/senha/esqueci", methods=["GET", "POST"])
def esqueci_senha():
    """Recebe o e-mail e dispara o link de redefinição, se a conta existir.

    A resposta é sempre a mesma, exista a conta ou não.
    """
    if current_user.is_authenticated:
        return redirect(url_for("auth.alterar_senha"))

    form = EsqueciSenhaForm()
    if form.validate_on_submit():
        email = Usuario.normalizar_email(form.email.data)

        bloqueio = seguranca.verificar(seguranca.RESET, email)
        if bloqueio:
            flash(_mensagem_bloqueio(bloqueio.minutos_restantes), "erro")
            return render_template("auth/esqueci_senha.html", form=form)

        # Registrada antes de saber se a conta existe: o limite precisa valer
        # igual para e-mails inexistentes, senão vira sonda de enumeração.
        seguranca.registrar(seguranca.RESET, email, sucesso=False)

        usuario = Usuario.query.filter_by(email=email).first()
        if usuario and usuario.ativo:
            link = url_for(
                "auth.redefinir_senha", token=tokens.gerar(usuario), _external=True
            )
            mailer.enviar(
                usuario.email,
                "Redefinição de senha — Fluxo de Caixa",
                "Você pediu para redefinir sua senha.\n\n"
                f"Acesse o link abaixo para escolher uma nova:\n{link}\n\n"
                "O link vale por 1 hora e só pode ser usado uma vez.\n"
                "Se não foi você, ignore esta mensagem: nada muda.\n",
            )

        flash(RESET_SOLICITADO, "sucesso")
        return redirect(url_for("auth.login"))

    return render_template("auth/esqueci_senha.html", form=form)


@bp.route("/senha/redefinir/<token>", methods=["GET", "POST"])
def redefinir_senha(token: str):
    """Valida o link e troca a senha.

    Não pede a senha atual: quem chega aqui provou ter acesso ao e-mail.
    """
    usuario = tokens.validar(token)
    if usuario is None:
        flash("Link inválido ou expirado. Peça um novo.", "erro")
        return redirect(url_for("auth.esqueci_senha"))

    form = RedefinirSenhaForm()
    if form.validate_on_submit():
        usuario.definir_senha(form.nova_senha.data)
        db.session.commit()

        # Trocar a senha destrava a conta: quem provou o e-mail não deve
        # ficar preso ao bloqueio causado por quem errou a senha antes.
        seguranca.limpar_apos_sucesso(seguranca.LOGIN, usuario.email)
        seguranca.limpar_apos_sucesso(seguranca.RESET, usuario.email)

        flash("Senha redefinida. Faça login com a nova senha.", "sucesso")
        return redirect(url_for("auth.login"))

    return render_template("auth/redefinir_senha.html", form=form)


@bp.route("/conta/senha", methods=["GET", "POST"])
@login_required
def alterar_senha():
    """Troca de senha por quem já está autenticado, exigindo a senha atual."""
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
