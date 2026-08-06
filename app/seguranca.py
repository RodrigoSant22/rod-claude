"""Freio de força bruta para login e redefinição de senha.

A contagem fica no banco, não em memória: assim o limite sobrevive a
reinícios do servidor e vale para todos os processos quando há mais de um.

Duas contagens em paralelo:

- **por conta** — impede martelar a senha de um e-mail específico;
- **por IP** — impede varrer muitos e-mails a partir do mesmo lugar.

Contamos o e-mail *tentado*, exista ele ou não. Contar só contas reais
deixaria a varredura de e-mails livre, que é justamente o que revelaria
quais endereços têm conta.
"""

from dataclasses import dataclass
from datetime import timedelta

from flask import current_app, request

from app.extensions import db
from app.models import TentativaAcesso, Usuario, utcnow

LOGIN = "login"
RESET = "reset"

# Configuração de cada ação: (limite por conta, limite por IP, janela).
_POLITICAS = {
    LOGIN: ("LOGIN_MAX_POR_CONTA", "LOGIN_MAX_POR_IP", "LOGIN_JANELA"),
    RESET: ("RESET_MAX_POR_CONTA", "RESET_MAX_POR_IP", "RESET_JANELA"),
}


@dataclass(frozen=True)
class Bloqueio:
    """Veredito do freio, com a espera restante quando há bloqueio."""

    bloqueado: bool
    minutos_restantes: int = 0

    def __bool__(self) -> bool:
        """Permite escrever `if bloqueio:` em vez de `if bloqueio.bloqueado:`."""
        return self.bloqueado


def ip_do_pedido() -> str | None:
    """IP de origem.

    Atrás de proxy reverso, `remote_addr` é o do proxy — quem for expor a
    aplicação assim precisa configurar ProxyFix para o valor ser real.
    """
    return request.remote_addr if request else None


def registrar(acao: str, identificador: str, sucesso: bool) -> None:
    """Grava uma tentativa. Só as falhas contam para o limite."""
    db.session.add(
        TentativaAcesso(
            acao=acao,
            identificador=Usuario.normalizar_email(identificador),
            ip=ip_do_pedido(),
            sucesso=sucesso,
        )
    )
    db.session.commit()


def limpar_apos_sucesso(acao: str, identificador: str) -> None:
    """Zera o contador da conta: acertar a senha não deve deixar resíduo."""
    TentativaAcesso.query.filter_by(
        acao=acao, identificador=Usuario.normalizar_email(identificador), sucesso=False
    ).delete()
    db.session.commit()


def _falhas_desde(acao: str, desde, **filtros) -> int:
    """Conta as falhas na janela, filtrando por conta ou por IP.

    Os `**filtros` viram condições via `getattr`, o que evita duplicar a
    função para cada campo.
    """
    return TentativaAcesso.query.filter(
        TentativaAcesso.acao == acao,
        TentativaAcesso.sucesso.is_(False),
        TentativaAcesso.criado_em >= desde,
        *[getattr(TentativaAcesso, campo) == valor for campo, valor in filtros.items()],
    ).count()


def _espera_restante(acao: str, desde, **filtros) -> int:
    """Minutos até a tentativa mais antiga da janela expirar."""
    mais_antiga = (
        TentativaAcesso.query.filter(
            TentativaAcesso.acao == acao,
            TentativaAcesso.sucesso.is_(False),
            TentativaAcesso.criado_em >= desde,
            *[getattr(TentativaAcesso, campo) == valor for campo, valor in filtros.items()],
        )
        .order_by(TentativaAcesso.criado_em)
        .first()
    )
    if mais_antiga is None:
        return 0

    janela: timedelta = current_app.config[_POLITICAS[acao][2]]
    # O banco pode devolver datetime sem fuso; assume-se UTC, que é como grava.
    criado = mais_antiga.criado_em
    if criado.tzinfo is None:
        criado = criado.replace(tzinfo=utcnow().tzinfo)

    faltam = (criado + janela) - utcnow()
    return max(1, int(faltam.total_seconds() // 60) + 1)


def verificar(acao: str, identificador: str) -> Bloqueio:
    """Diz se a ação deve ser recusada agora por excesso de tentativas."""
    chave_conta, chave_ip, chave_janela = _POLITICAS[acao]
    limite_conta = current_app.config[chave_conta]
    limite_ip = current_app.config[chave_ip]
    desde = utcnow() - current_app.config[chave_janela]

    email = Usuario.normalizar_email(identificador)
    if _falhas_desde(acao, desde, identificador=email) >= limite_conta:
        return Bloqueio(True, _espera_restante(acao, desde, identificador=email))

    ip = ip_do_pedido()
    if ip and _falhas_desde(acao, desde, ip=ip) >= limite_ip:
        return Bloqueio(True, _espera_restante(acao, desde, ip=ip))

    return Bloqueio(False)


def limpar_antigas(dias: int = 30) -> int:
    """Descarta registros velhos — a tabela não precisa crescer para sempre."""
    corte = utcnow() - timedelta(days=dias)
    removidas = TentativaAcesso.query.filter(TentativaAcesso.criado_em < corte).delete()
    db.session.commit()
    return removidas
