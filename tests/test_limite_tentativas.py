"""Freio de força bruta no login e no pedido de redefinição."""

from datetime import timedelta

from app.extensions import db
from app.models import TentativaAcesso, utcnow
from tests.conftest import SENHA


def errar(client, email: str, vezes: int = 1):
    for _ in range(vezes):
        resposta = client.post(
            "/login", data={"email": email, "senha": "chute"}, follow_redirects=True
        )
    return resposta


def envelhecer(minutos: int) -> None:
    """Empurra as tentativas para o passado, simulando o tempo passando."""
    for tentativa in TentativaAcesso.query.all():
        tentativa.criado_em = utcnow() - timedelta(minutes=minutos)
    db.session.commit()


def test_erros_abaixo_do_limite_nao_bloqueiam(client, usuario):
    corpo = errar(client, usuario.email, 4).get_data(as_text=True)

    assert "E-mail ou senha incorretos" in corpo
    assert "Muitas tentativas" not in corpo


def test_bloqueia_no_quinto_erro(client, usuario):
    errar(client, usuario.email, 5)

    corpo = errar(client, usuario.email).get_data(as_text=True)
    assert "Muitas tentativas" in corpo


def test_bloqueio_recusa_ate_a_senha_correta(client, usuario):
    """Ponto central: bloqueado, nem a senha certa entra."""
    errar(client, usuario.email, 5)

    resp = client.post(
        "/login", data={"email": usuario.email, "senha": SENHA}, follow_redirects=True
    )

    assert "Muitas tentativas" in resp.get_data(as_text=True)
    assert "Painel" not in resp.get_data(as_text=True)


def test_acerto_antes_do_limite_zera_o_contador(client, usuario):
    errar(client, usuario.email, 4)

    entrou = client.post(
        "/login", data={"email": usuario.email, "senha": SENHA}, follow_redirects=True
    )
    assert "Painel" in entrou.get_data(as_text=True)

    assert TentativaAcesso.query.filter_by(sucesso=False).count() == 0


def test_bloqueio_expira_com_a_janela(client, usuario):
    errar(client, usuario.email, 5)
    envelhecer(16)  # a janela padrão é de 15 minutos

    resp = client.post(
        "/login", data={"email": usuario.email, "senha": SENHA}, follow_redirects=True
    )

    assert "Painel" in resp.get_data(as_text=True)


def test_bloqueio_e_por_conta_nao_global(client, usuario, outro_usuario):
    """Travar uma conta não pode travar as outras."""
    errar(client, usuario.email, 5)

    resp = client.post(
        "/login", data={"email": outro_usuario.email, "senha": SENHA}, follow_redirects=True
    )

    assert "Painel" in resp.get_data(as_text=True)


def test_email_inexistente_tambem_conta(client, db):
    """Se só contasse conta real, varrer e-mails ficaria livre."""
    errar(client, "ninguem@exemplo.com", 5)

    corpo = errar(client, "ninguem@exemplo.com").get_data(as_text=True)
    assert "Muitas tentativas" in corpo


def test_limite_por_ip_conta_emails_diferentes(client, db):
    """Varredura de muitos e-diferentes do mesmo IP também é barrada."""
    for numero in range(20):
        errar(client, f"alvo{numero}@exemplo.com")

    corpo = errar(client, "mais-um@exemplo.com").get_data(as_text=True)
    assert "Muitas tentativas" in corpo


def test_mensagem_informa_a_espera(client, usuario):
    errar(client, usuario.email, 5)

    corpo = errar(client, usuario.email).get_data(as_text=True)
    assert "minuto" in corpo


def test_limpar_antigas_remove_so_o_que_passou_do_prazo(app, db, usuario):
    db.session.add_all(
        [
            TentativaAcesso(acao="login", identificador="a@b.com", criado_em=utcnow()),
            TentativaAcesso(
                acao="login",
                identificador="c@d.com",
                criado_em=utcnow() - timedelta(days=40),
            ),
        ]
    )
    db.session.commit()

    runner = app.test_cli_runner()
    resultado = runner.invoke(args=["limpar-tentativas"])

    assert "1 registro(s) removido(s)" in resultado.output
    assert TentativaAcesso.query.count() == 1
