"""Envio de e-mail por SMTP, com queda para o log.

Sem `MAIL_SERVER` configurado, a mensagem é escrita no log do servidor em
vez de enviada. É o que torna a recuperação de senha utilizável numa
instalação local, onde não há SMTP à mão: o link aparece no terminal onde
o `flask run` está rodando.
"""

import smtplib
from email.message import EmailMessage

from flask import current_app


def enviar(destino: str, assunto: str, corpo: str) -> bool:
    """Devolve True se saiu por SMTP, False se caiu no log."""
    servidor = current_app.config.get("MAIL_SERVER")

    if not servidor:
        # WARNING, e não INFO: fora do modo debug o Flask descarta INFO, e a
        # mensagem não apareceria justamente em quem depende dela para pegar
        # o link. Não enviar um e-mail pedido é mesmo uma condição anormal.
        current_app.logger.warning(
            "\n%s\nE-MAIL NÃO ENVIADO (MAIL_SERVER não configurado)\n"
            "Para: %s\nAssunto: %s\n\n%s\n%s",
            "=" * 70, destino, assunto, corpo, "=" * 70,
        )
        return False

    mensagem = EmailMessage()
    mensagem["Subject"] = assunto
    mensagem["From"] = current_app.config["MAIL_FROM"]
    mensagem["To"] = destino
    mensagem.set_content(corpo)

    try:
        with smtplib.SMTP(servidor, current_app.config["MAIL_PORT"], timeout=15) as smtp:
            if current_app.config.get("MAIL_USE_TLS"):
                smtp.starttls()
            usuario = current_app.config.get("MAIL_USERNAME")
            if usuario:
                smtp.login(usuario, current_app.config["MAIL_PASSWORD"])
            smtp.send_message(mensagem)
        return True
    except (smtplib.SMTPException, OSError):
        # Falha de envio não pode derrubar o pedido nem revelar ao visitante
        # que aquele e-mail existe.
        current_app.logger.exception("Falha ao enviar e-mail para %s", destino)
        return False
