"""Tokens assinados para redefinição de senha.

Não há tabela de tokens: o próprio token carrega a informação, assinada
com o `SECRET_KEY`. Quem alterar um byte invalida a assinatura.

O token é de uso único sem precisar de estado no banco — ele embute uma
parte do hash da senha atual. Assim que a senha muda, o hash muda e o
token deixa de conferir, o que também invalida qualquer link antigo que
tenha vazado.
"""

import hashlib

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.extensions import db
from app.models import Usuario

_SAL = "redefinir-senha"


def _serializador() -> URLSafeTimedSerializer:
    """Assinador ligado ao SECRET_KEY atual.

    Criado a cada chamada, e não uma vez no módulo, para respeitar a
    configuração do app em uso — o que importa nos testes.
    """
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=_SAL)


def _impressao(usuario: Usuario) -> str:
    """Resumo curto do hash atual — muda junto com a senha."""
    return hashlib.sha256(usuario.senha_hash.encode()).hexdigest()[:16]


def gerar(usuario: Usuario) -> str:
    """Cria o token do link de redefinição para este usuário."""
    return _serializador().dumps({"id": usuario.id, "h": _impressao(usuario)})


def validar(token: str) -> Usuario | None:
    """Devolve o usuário do token, ou None se inválido, expirado ou já usado."""
    validade = current_app.config["RESET_TOKEN_VALIDADE"]

    try:
        dados = _serializador().loads(token, max_age=validade.total_seconds())
    except (BadSignature, SignatureExpired):
        return None

    if not isinstance(dados, dict):
        return None

    usuario = db.session.get(Usuario, dados.get("id"))
    if usuario is None or not usuario.ativo:
        return None

    # Confere a impressão do hash: senha já trocada invalida o token.
    if dados.get("h") != _impressao(usuario):
        return None

    return usuario
