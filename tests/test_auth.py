"""Login, logout e as proteções em volta deles."""

from app import create_app
from app.models import Usuario
from tests.conftest import SENHA

ROTAS_PROTEGIDAS = [
    "/",
    "/lancamentos/",
    "/lancamentos/novo",
    "/categorias/",
    "/categorias/nova",
    "/conta/senha",
]


def test_senha_nunca_e_guardada_em_texto(db, usuario):
    assert usuario.senha_hash != SENHA
    assert SENHA not in usuario.senha_hash


def test_configuracao_padrao_usa_scrypt(db):
    """O hash barato vale só nos testes; fora deles tem que ser scrypt."""
    from app.config import DevelopmentConfig, ProductionConfig

    assert not hasattr(ProductionConfig, "PASSWORD_HASH_METHOD")
    assert not hasattr(DevelopmentConfig, "PASSWORD_HASH_METHOD")

    usuario = Usuario(nome="Real", email="real@exemplo.com")
    with create_app(DevelopmentConfig).app_context():
        usuario.definir_senha("qualquer-senha")

    assert usuario.senha_hash.startswith("scrypt:")


def test_conferir_senha(usuario):
    assert usuario.conferir_senha(SENHA) is True
    assert usuario.conferir_senha("errada") is False


def test_email_e_normalizado():
    assert Usuario.normalizar_email("  Rodrigo@Exemplo.COM ") == "rodrigo@exemplo.com"


def test_rotas_protegidas_redirecionam_para_login(client):
    for rota in ROTAS_PROTEGIDAS:
        resp = client.get(rota)
        assert resp.status_code == 302, rota
        assert "/login" in resp.headers["Location"], rota


def test_health_continua_publica(client):
    assert client.get("/health").status_code == 200


def test_login_com_credenciais_corretas(client, usuario):
    resp = client.post(
        "/login", data={"email": usuario.email, "senha": SENHA}, follow_redirects=True
    )

    assert resp.status_code == 200
    assert "Painel" in resp.get_data(as_text=True)


def test_login_aceita_email_com_maiusculas(client, usuario):
    resp = client.post(
        "/login", data={"email": "RODRIGO@EXEMPLO.COM", "senha": SENHA}, follow_redirects=True
    )

    assert "Painel" in resp.get_data(as_text=True)


def test_login_com_senha_errada_falha(client, usuario):
    resp = client.post(
        "/login", data={"email": usuario.email, "senha": "errada"}, follow_redirects=True
    )

    assert "E-mail ou senha incorretos" in resp.get_data(as_text=True)


def test_mensagem_nao_revela_se_o_email_existe(client, usuario):
    """Mensagens diferentes permitiriam descobrir quais e-mails têm conta."""
    inexistente = client.post(
        "/login", data={"email": "ninguem@exemplo.com", "senha": "x"}, follow_redirects=True
    ).get_data(as_text=True)
    senha_errada = client.post(
        "/login", data={"email": usuario.email, "senha": "x"}, follow_redirects=True
    ).get_data(as_text=True)

    assert "E-mail ou senha incorretos" in inexistente
    assert "E-mail ou senha incorretos" in senha_errada


def test_usuario_desativado_nao_entra(client, db, usuario):
    usuario.ativo = False
    db.session.commit()

    resp = client.post(
        "/login", data={"email": usuario.email, "senha": SENHA}, follow_redirects=True
    )

    assert "E-mail ou senha incorretos" in resp.get_data(as_text=True)


def test_logout_encerra_a_sessao(logado):
    logado.post("/logout", follow_redirects=True)

    assert logado.get("/lancamentos/").status_code == 302


def test_next_leva_a_pagina_pedida(client, usuario):
    resp = client.post(
        "/login?next=/categorias/",
        data={"email": usuario.email, "senha": SENHA},
    )

    assert resp.headers["Location"] == "/categorias/"


def test_next_externo_e_ignorado(client, usuario):
    """Sem isso, o login viraria redirecionador aberto para phishing."""
    for destino in ["https://malicioso.example", "//malicioso.example", "http://x.example/a"]:
        resp = client.post(
            f"/login?next={destino}", data={"email": usuario.email, "senha": SENHA}
        )
        assert resp.headers["Location"] == "/", destino


def test_ja_logado_e_desviado_do_login(logado):
    resp = logado.get("/login")

    assert resp.status_code == 302
    assert resp.headers["Location"] == "/"


def test_alterar_senha(logado, db, usuario):
    logado.post(
        "/conta/senha",
        data={
            "senha_atual": SENHA,
            "nova_senha": "nova-senha-longa",
            "confirmacao": "nova-senha-longa",
        },
        follow_redirects=True,
    )

    db.session.refresh(usuario)
    assert usuario.conferir_senha("nova-senha-longa")


def test_alterar_senha_exige_a_atual(logado, db, usuario):
    resp = logado.post(
        "/conta/senha",
        data={
            "senha_atual": "chute",
            "nova_senha": "nova-senha-longa",
            "confirmacao": "nova-senha-longa",
        },
        follow_redirects=True,
    )

    assert "Senha atual incorreta" in resp.get_data(as_text=True)
    db.session.refresh(usuario)
    assert usuario.conferir_senha(SENHA)


def test_nova_senha_curta_e_recusada(logado, db, usuario):
    logado.post(
        "/conta/senha",
        data={"senha_atual": SENHA, "nova_senha": "curta", "confirmacao": "curta"},
        follow_redirects=True,
    )

    db.session.refresh(usuario)
    assert usuario.conferir_senha(SENHA)


def test_confirmacao_divergente_e_recusada(logado, db, usuario):
    resp = logado.post(
        "/conta/senha",
        data={
            "senha_atual": SENHA,
            "nova_senha": "nova-senha-longa",
            "confirmacao": "outra-senha-longa",
        },
        follow_redirects=True,
    )

    assert "não conferem" in resp.get_data(as_text=True)
    db.session.refresh(usuario)
    assert usuario.conferir_senha(SENHA)
