"""Fluxo de redefinição de senha por link assinado."""

import re
import time
from datetime import timedelta

from app import tokens
from tests.conftest import SENHA

NOVA = "senha-nova-bem-longa"


def pedir(client, email: str):
    return client.post("/senha/esqueci", data={"email": email}, follow_redirects=True)


def link_do_log(caplog) -> str:
    """Sem SMTP configurado, o link vai para o log — é de lá que o extraímos."""
    achado = re.search(r"(/senha/redefinir/[\w\-\.]+)", caplog.text)
    assert achado, f"link não encontrado no log:\n{caplog.text}"
    return achado.group(1)


def test_pedido_gera_link(client, usuario, caplog):
    with caplog.at_level("INFO"):
        resp = pedir(client, usuario.email)

    assert "enviamos as instruções" in resp.get_data(as_text=True)
    assert link_do_log(caplog)


def test_link_e_registrado_em_nivel_warning(client, usuario, caplog):
    """Em INFO a mensagem sumiria: fora do modo debug o Flask descarta INFO,
    e o link não chegaria a quem depende do log para recebê-lo."""
    with caplog.at_level("DEBUG"):
        pedir(client, usuario.email)

    registros = [r for r in caplog.records if "/senha/redefinir/" in r.getMessage()]
    assert registros, "nenhum registro com o link"
    assert all(r.levelname == "WARNING" for r in registros)


def test_email_inexistente_da_a_mesma_resposta(client, db, usuario, caplog):
    """A resposta não pode revelar quais e-mails têm conta."""
    real = pedir(client, usuario.email).get_data(as_text=True)
    falso = pedir(client, "ninguem@exemplo.com").get_data(as_text=True)

    assert "enviamos as instruções" in real
    assert "enviamos as instruções" in falso


def test_nenhum_email_e_gerado_para_conta_inexistente(client, db, caplog):
    with caplog.at_level("INFO"):
        pedir(client, "ninguem@exemplo.com")

    assert "/senha/redefinir/" not in caplog.text


def test_fluxo_completo_troca_a_senha(client, db, usuario, caplog):
    with caplog.at_level("INFO"):
        pedir(client, usuario.email)
    link = link_do_log(caplog)

    assert client.get(link).status_code == 200

    client.post(link, data={"nova_senha": NOVA, "confirmacao": NOVA}, follow_redirects=True)

    db.session.refresh(usuario)
    assert usuario.conferir_senha(NOVA)
    assert not usuario.conferir_senha(SENHA)


def test_token_e_de_uso_unico(client, db, usuario, caplog):
    with caplog.at_level("INFO"):
        pedir(client, usuario.email)
    link = link_do_log(caplog)

    client.post(link, data={"nova_senha": NOVA, "confirmacao": NOVA}, follow_redirects=True)

    # Segunda tentativa com o mesmo link: a senha já mudou, o token não vale.
    resp = client.post(
        link,
        data={"nova_senha": "outra-senha-longa", "confirmacao": "outra-senha-longa"},
        follow_redirects=True,
    )

    assert "Link inválido ou expirado" in resp.get_data(as_text=True)
    db.session.refresh(usuario)
    assert usuario.conferir_senha(NOVA)


def test_token_adulterado_e_recusado(client, usuario):
    resp = client.get("/senha/redefinir/token-inventado", follow_redirects=True)

    assert "Link inválido ou expirado" in resp.get_data(as_text=True)


def test_token_expirado_e_recusado(app, db, usuario):
    # O itsdangerous mede idade em segundos inteiros: com validade 0, basta
    # cruzar uma fronteira de segundo para o token estar velho demais.
    app.config["RESET_TOKEN_VALIDADE"] = timedelta(seconds=0)
    token = tokens.gerar(usuario)
    time.sleep(1.1)

    assert tokens.validar(token) is None


def test_token_dentro_da_validade_e_aceito(app, db, usuario):
    """Contraprova: o teste acima falharia por qualquer motivo, não só idade."""
    token = tokens.gerar(usuario)

    assert tokens.validar(token) is usuario


def test_token_de_conta_desativada_e_recusado(app, db, usuario):
    token = tokens.gerar(usuario)
    usuario.ativo = False
    db.session.commit()

    assert tokens.validar(token) is None


def test_alterar_a_senha_invalida_token_pendente(app, db, usuario):
    """Link antigo que tenha vazado deixa de servir quando a senha muda."""
    token = tokens.gerar(usuario)

    usuario.definir_senha("trocada-por-outro-caminho")
    db.session.commit()

    assert tokens.validar(token) is None


def test_confirmacao_divergente_nao_troca(client, db, usuario, caplog):
    with caplog.at_level("INFO"):
        pedir(client, usuario.email)
    link = link_do_log(caplog)

    client.post(
        link, data={"nova_senha": NOVA, "confirmacao": "diferente"}, follow_redirects=True
    )

    db.session.refresh(usuario)
    assert usuario.conferir_senha(SENHA)


def test_senha_curta_nao_troca(client, db, usuario, caplog):
    with caplog.at_level("INFO"):
        pedir(client, usuario.email)
    link = link_do_log(caplog)

    client.post(link, data={"nova_senha": "curta", "confirmacao": "curta"}, follow_redirects=True)

    db.session.refresh(usuario)
    assert usuario.conferir_senha(SENHA)


def test_pedidos_em_excesso_sao_barrados(client, usuario):
    for _ in range(3):
        pedir(client, usuario.email)

    resp = pedir(client, usuario.email)
    assert "Muitas tentativas" in resp.get_data(as_text=True)


def test_redefinir_destrava_conta_bloqueada(client, db, usuario, caplog):
    """Quem prova o e-mail não deve ficar preso ao bloqueio do login."""
    for _ in range(5):
        client.post("/login", data={"email": usuario.email, "senha": "chute"})

    with caplog.at_level("INFO"):
        pedir(client, usuario.email)
    link = link_do_log(caplog)
    client.post(link, data={"nova_senha": NOVA, "confirmacao": NOVA}, follow_redirects=True)

    entrou = client.post(
        "/login", data={"email": usuario.email, "senha": NOVA}, follow_redirects=True
    )

    assert "Painel" in entrou.get_data(as_text=True)


def test_logado_e_desviado_para_alterar_senha(logado):
    resp = logado.get("/senha/esqueci")

    assert resp.status_code == 302
    assert "/conta/senha" in resp.headers["Location"]
