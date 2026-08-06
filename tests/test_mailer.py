"""Envio por SMTP e a queda para o log."""

import smtplib

import pytest

from app import mailer


class SMTPFalso:
    """Substitui smtplib.SMTP e registra o que foi chamado."""

    instancias: list["SMTPFalso"] = []

    def __init__(self, servidor, porta, timeout=None):
        """Guarda os parâmetros da conexão em vez de abrir uma de verdade."""
        self.servidor = servidor
        self.porta = porta
        self.timeout = timeout
        self.tls = False
        self.login_com = None
        self.mensagens = []
        SMTPFalso.instancias.append(self)

    def __enter__(self):
        """Suporte ao `with`, como o smtplib.SMTP real."""
        return self

    def __exit__(self, *args):
        """Não engole exceções."""
        return False

    def starttls(self):
        """Registra que o TLS foi solicitado."""
        self.tls = True

    def login(self, usuario, senha):
        """Registra as credenciais recebidas."""
        self.login_com = (usuario, senha)

    def send_message(self, mensagem):
        """Guarda a mensagem para o teste inspecionar."""
        self.mensagens.append(mensagem)


@pytest.fixture
def smtp(monkeypatch):
    """Troca smtplib.SMTP pelo dublê e devolve a classe, para inspeção."""
    SMTPFalso.instancias = []
    monkeypatch.setattr(smtplib, "SMTP", SMTPFalso)
    return SMTPFalso


def configurar(app, **extras):
    """Preenche a config de SMTP, permitindo sobrescrever chaves pontuais."""
    padrao = {
        "MAIL_SERVER": "smtp.exemplo.com",
        "MAIL_PORT": 587,
        "MAIL_USE_TLS": True,
        "MAIL_USERNAME": None,
        "MAIL_PASSWORD": None,
        "MAIL_FROM": "nao-responda@exemplo.com",
    }
    app.config.update({**padrao, **extras})


def test_sem_servidor_cai_no_log(app, caplog):
    app.config["MAIL_SERVER"] = None

    with caplog.at_level("DEBUG"):
        enviado = mailer.enviar("alguem@exemplo.com", "Assunto", "Corpo da mensagem")

    assert enviado is False
    assert "Corpo da mensagem" in caplog.text


def test_com_servidor_envia(app, smtp):
    configurar(app)

    enviado = mailer.enviar("alguem@exemplo.com", "Assunto", "Corpo")

    assert enviado is True
    assert len(smtp.instancias) == 1

    conexao = smtp.instancias[0]
    assert conexao.servidor == "smtp.exemplo.com"
    assert conexao.tls is True
    assert conexao.login_com is None  # sem MAIL_USERNAME, não autentica

    mensagem = conexao.mensagens[0]
    assert mensagem["To"] == "alguem@exemplo.com"
    assert mensagem["Subject"] == "Assunto"
    assert mensagem["From"] == "nao-responda@exemplo.com"
    assert "Corpo" in mensagem.get_content()


def test_autentica_quando_ha_usuario(app, smtp):
    configurar(app, MAIL_USERNAME="conta@exemplo.com", MAIL_PASSWORD="segredo")

    mailer.enviar("alguem@exemplo.com", "Assunto", "Corpo")

    assert smtp.instancias[0].login_com == ("conta@exemplo.com", "segredo")


def test_sem_tls_nao_chama_starttls(app, smtp):
    configurar(app, MAIL_USE_TLS=False)

    mailer.enviar("alguem@exemplo.com", "Assunto", "Corpo")

    assert smtp.instancias[0].tls is False


def test_falha_de_envio_nao_propaga(app, monkeypatch, caplog):
    """Erro de SMTP não pode derrubar o pedido nem vazar que a conta existe."""
    configurar(app)

    def explode(*a, **kw):
        """Simula o servidor recusando a conexão."""
        raise smtplib.SMTPException("servidor recusou")

    monkeypatch.setattr(smtplib, "SMTP", explode)

    enviado = mailer.enviar("alguem@exemplo.com", "Assunto", "Corpo")

    assert enviado is False
    assert "Falha ao enviar" in caplog.text


def test_servidor_inacessivel_nao_propaga(app, monkeypatch):
    configurar(app)

    def sem_rota(*a, **kw):
        """Simula falha de rede antes do SMTP."""
        raise OSError("sem rota para o host")

    monkeypatch.setattr(smtplib, "SMTP", sem_rota)

    assert mailer.enviar("alguem@exemplo.com", "Assunto", "Corpo") is False


def test_pedido_de_reset_sobrevive_a_falha_de_smtp(app, client, usuario, monkeypatch):
    """A resposta ao visitante é a mesma, envio tendo funcionado ou não."""
    configurar(app)
    monkeypatch.setattr(
        smtplib, "SMTP", lambda *a, **kw: (_ for _ in ()).throw(smtplib.SMTPException())
    )

    resp = client.post(
        "/senha/esqueci", data={"email": usuario.email}, follow_redirects=True
    )

    assert resp.status_code == 200
    assert "enviamos as instruções" in resp.get_data(as_text=True)
