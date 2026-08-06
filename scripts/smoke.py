"""Teste de fumaça: exercita a aplicação rodando de verdade, por HTTP.

Complementa o pytest, que desliga CSRF e usa hash barato para ganhar
velocidade. Aqui nada é desligado: o servidor sobe com a configuração de
desenvolvimento, e as requisições passam por rede, cookies e sessão.

Uso mais simples — prepara tudo num banco temporário e limpa no fim:

    python scripts/smoke.py

Contra um servidor que já está rodando, com contas que já existem:

    python scripts/smoke.py --url http://127.0.0.1:5000 \
        --email eu@exemplo.com --senha minha-senha

Sai com código 0 se tudo passar, 1 se algo falhar.
"""

from __future__ import annotations

import argparse
import http.cookiejar
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

CONTA = ("smoke-um@exemplo.com", "senha-de-fumaca-1")
CONTA2 = ("smoke-dois@exemplo.com", "senha-de-fumaca-2")
# Conta separada para o teste de redefinição, que troca a senha.
CONTA3 = ("smoke-tres@exemplo.com", "senha-de-fumaca-3")


# --------------------------------------------------------------------------
# Relatório
# --------------------------------------------------------------------------

falhas: list[str] = []


def checa(rotulo: str, condicao: bool, detalhe: str = "") -> None:
    """Imprime o resultado de uma verificação e guarda as que falharem."""
    print(f"{'  ok  ' if condicao else ' FALHA'} │ {rotulo} {detalhe}")
    if not condicao:
        falhas.append(rotulo)


def secao(titulo: str) -> None:
    """Imprime o cabeçalho de um grupo de verificações."""
    print(f"\n── {titulo} " + "─" * max(0, 58 - len(titulo)))


# --------------------------------------------------------------------------
# Cliente HTTP
# --------------------------------------------------------------------------


class Sessao:
    """Cliente com cookies próprios — cada instância é um "navegador"."""

    def __init__(self, base: str):
        """Prepara um cliente com cookiejar próprio, apontando para `base`."""
        self.base = base.rstrip("/")
        # ProxyHandler vazio ignora HTTP_PROXY do ambiente: 127.0.0.1 é local.
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
            urllib.request.ProxyHandler({}),
        )

    def get(self, caminho: str) -> tuple[int, str]:
        """GET seguindo redirecionamentos. Devolve (status, corpo em texto)."""
        with self.opener.open(self.base + caminho) as r:
            # utf-8-sig descarta o BOM do CSV, que atrapalharia as buscas.
            return r.status, r.read().decode("utf-8-sig")

    def bytes(self, caminho: str) -> bytes:
        """Conteúdo cru — para binários como o xlsx."""
        with self.opener.open(self.base + caminho) as r:
            return r.read()

    def post(self, caminho: str, dados: dict, token: str | None = None) -> tuple[int, str]:
        """POST em formulário. Passe `token` para incluir o csrf_token."""
        if token:
            dados = {**dados, "csrf_token": token}
        corpo = urllib.parse.urlencode(dados).encode()
        with self.opener.open(self.base + caminho, data=corpo) as r:
            return r.status, r.read().decode()

    def post_cru(self, caminho: str, dados: dict) -> int:
        """POST sem tratar erro — devolve o código, inclusive 4xx."""
        try:
            return self.post(caminho, dados)[0]
        except urllib.error.HTTPError as e:
            return e.code

    def redirecionamento(self, caminho: str) -> tuple[int, str | None]:
        """Segue nada: devolve o status e o Location, para checar desvios."""

        class SemRedirect(urllib.request.HTTPRedirectHandler):
            """Handler que não segue redirecionamento, para inspecionar o 302."""

            def redirect_request(self, *a, **kw):
                """Devolver None faz o urllib parar no redirecionamento."""
                return None

        op = urllib.request.build_opener(
            SemRedirect,
            urllib.request.HTTPCookieProcessor(self._jar()),
            urllib.request.ProxyHandler({}),
        )
        try:
            with op.open(self.base + caminho) as r:
                return r.status, r.headers.get("Location")
        except urllib.error.HTTPError as e:
            return e.code, e.headers.get("Location")

    def _jar(self):
        """Devolve o cookiejar desta sessão, para reaproveitá-lo."""
        for h in self.opener.handlers:
            if isinstance(h, urllib.request.HTTPCookieProcessor):
                return h.cookiejar
        raise RuntimeError("sessão sem cookiejar")

    def entrar(self, email: str, senha: str) -> str:
        """Faz login e devolve o HTML da página de destino."""
        _, html = self.get("/login")
        _, html = self.post("/login", {"email": email, "senha": senha}, token_de(html))
        return html


def token_de(html: str) -> str:
    """Extrai o csrf_token do HTML. Levanta se não houver."""
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    if not achado:
        raise RuntimeError("csrf_token não encontrado no HTML")
    return achado.group(1)


# --------------------------------------------------------------------------
# Ambiente temporário
# --------------------------------------------------------------------------


def porta_livre() -> int:
    """Uma porta livre no sistema.

    Porta 0 faz o sistema escolher; lê-se qual foi e devolve o número.
    """
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def flask(ambiente: dict, *args: str) -> None:
    """Executa um comando `flask` no ambiente dado. Levanta se falhar."""
    resultado = subprocess.run(
        [sys.executable, "-m", "flask", *args],
        cwd=RAIZ,
        env=ambiente,
        capture_output=True,
        text=True,
    )
    if resultado.returncode != 0:
        raise RuntimeError(f"flask {' '.join(args)} falhou:\n{resultado.stderr}")


def esperar_servidor(
    base: str, processo: subprocess.Popen, log: Path, limite: float = 30.0
) -> None:
    """Espera o servidor responder, ou levanta com o log se ele morrer."""
    inicio = time.monotonic()
    while time.monotonic() - inicio < limite:
        if processo.poll() is not None:
            saida = log.read_text() if log.exists() else "(sem log)"
            raise RuntimeError(f"servidor morreu ao subir:\n{saida}")
        try:
            Sessao(base).get("/health")
            return
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.3)
    raise RuntimeError(f"servidor não respondeu em {limite:.0f}s")


def preparar():
    """Sobe um servidor com banco temporário. Devolve (base, log, encerrar)."""
    pasta = Path(tempfile.mkdtemp(prefix="smoke-"))
    porta = porta_livre()
    base = f"http://127.0.0.1:{porta}"

    ambiente = {
        **os.environ,
        "FLASK_APP": "run.py",
        "FLASK_ENV": "development",
        "SECRET_KEY": "chave-efemera-do-smoke",
        "DATABASE_URL": f"sqlite:///{pasta / 'smoke.db'}",
    }

    print(f"preparando banco temporário em {pasta}")
    flask(ambiente, "db", "upgrade")
    for email, senha in (CONTA, CONTA2, CONTA3):
        flask(ambiente, "criar-usuario", "--email", email, "--nome", email.split("@")[0],
              "--senha", senha)
    flask(ambiente, "seed", "--email", CONTA[0])

    # Sem SMTP configurado, o link de redefinição vai para o log do servidor.
    # Gravando num arquivo, o script consegue lê-lo e seguir o fluxo inteiro.
    log = pasta / "servidor.log"
    print(f"subindo servidor em {base}")
    processo = subprocess.Popen(
        [sys.executable, "-m", "flask", "run", "--port", str(porta)],
        cwd=RAIZ,
        env=ambiente,
        stdout=log.open("w"),
        stderr=subprocess.STDOUT,
        text=True,
    )

    def encerrar():
        """Derruba o servidor e apaga a pasta temporária."""
        processo.terminate()
        try:
            processo.wait(timeout=10)
        except subprocess.TimeoutExpired:
            processo.kill()
        shutil.rmtree(pasta, ignore_errors=True)

    try:
        esperar_servidor(base, processo, log)
    except Exception:
        encerrar()
        raise

    return base, log, encerrar


# --------------------------------------------------------------------------
# Verificações
# --------------------------------------------------------------------------


def verificar(
    base: str,
    conta: tuple[str, str],
    conta2: tuple[str, str] | None,
    log: Path | None = None,
) -> None:
    """Roda todas as verificações contra o servidor em `base`.

    `conta2` habilita a checagem de isolamento; `log` habilita a de
    recuperação de senha, que precisa ler o link do log do servidor.
    """
    email, senha = conta

    secao("acesso sem login")
    anonimo = Sessao(base)
    for rota in ("/", "/lancamentos/", "/categorias/", "/conta/senha"):
        codigo, destino = anonimo.redirecionamento(rota)
        checa(f"{rota} exige login", codigo == 302 and "/login" in (destino or ""), f"→ {codigo}")

    codigo, _ = anonimo.get("/health")
    checa("/health é pública", codigo == 200)

    secao("autenticação")
    sessao = Sessao(base)
    _, html = sessao.get("/login")
    checa("página de login abre", "Entrar" in html)

    _, html = sessao.post("/login", {"email": email, "senha": "senha-errada"}, token_de(html))
    checa("senha errada é recusada", "E-mail ou senha incorretos" in html)

    _, html = sessao.post("/login", {"email": "ninguem@exemplo.com", "senha": "x"}, token_de(html))
    checa("e-mail inexistente dá a mesma mensagem", "E-mail ou senha incorretos" in html)

    html = sessao.entrar(email, senha)
    checa("login com credenciais corretas", "Painel" in html)

    secao("uso autenticado")
    _, html = sessao.get("/categorias/")
    checa("categorias aparecem", "Moradia" in html)

    _, html = sessao.get("/lancamentos/novo")
    token = token_de(html)
    opcao = re.search(r'<option value="(\d+)">Despesa · Moradia</option>', html)
    checa("formulário lista categorias", opcao is not None)
    if not opcao:
        return
    categoria = opcao.group(1)

    _, html = sessao.post(
        "/lancamentos/novo",
        {"descricao": "Aluguel do smoke", "valor": "1.850,45", "data": "2026-08-01",
         "categoria_id": categoria},
        token,
    )
    checa("lançamento é criado", "Lançamento registrado" in html)
    checa("valor formatado em pt-BR", "R$ 1.850,45" in html)

    _, html = sessao.post(
        "/lancamentos/novo",
        {"descricao": "Zerado", "valor": "0,00", "data": "2026-08-01",
         "categoria_id": categoria},
        token,
    )
    # Regressão real: com DataRequired, zero dizia "informe o valor".
    checa("valor zero traz a mensagem certa", "maior que zero" in html)

    _, html = sessao.get("/lancamentos/?texto=aluguel")
    checa("filtro por texto encontra", "Aluguel do smoke" in html)

    _, html = sessao.get("/lancamentos/?texto=coisa-que-nao-existe")
    checa("filtro sem resultado avisa", "Nenhum lançamento encontrado" in html)

    _, html = sessao.get("/")
    checa("painel soma o lançamento", "R$ 1.850,45" in html)

    secao("exportação")
    codigo, corpo_csv = sessao.get("/lancamentos/exportar.csv")
    checa("CSV é gerado", codigo == 200)
    checa("CSV traz o lançamento", "Aluguel do smoke" in corpo_csv)
    checa("CSV usa ponto e vírgula", corpo_csv.count(";") >= 5)

    bruto = sessao.bytes("/lancamentos/exportar.xlsx")
    checa("XLSX é gerado", bruto[:2] == b"PK", f"→ {len(bruto)} bytes")

    _, filtrado = sessao.get("/lancamentos/exportar.csv?texto=coisa-que-nao-existe")
    checa("exportação respeita o filtro", "Aluguel do smoke" not in filtrado)

    secao("proteção CSRF")
    codigo = sessao.post_cru(
        "/lancamentos/novo",
        {"descricao": "Sem token", "valor": "10,00", "data": "2026-08-01",
         "categoria_id": categoria},
    )
    checa("POST sem csrf_token é bloqueado", codigo == 400, f"→ HTTP {codigo}")

    if conta2:
        secao("isolamento entre contas")
        outra = Sessao(base)
        outra.entrar(*conta2)
        _, html = outra.get("/lancamentos/")
        checa("outra conta não vê o lançamento", "Aluguel do smoke" not in html)
        checa("outra conta não vê a categoria", "Moradia" not in html)

    secao("logout")
    _, html = sessao.get("/")
    sessao.post("/logout", {}, token_de(html))
    codigo, destino = sessao.redirecionamento("/lancamentos/")
    checa("sessão é encerrada", codigo == 302 and "/login" in (destino or ""))

    secao("limite de tentativas")
    # E-mail inventado: assim o freio é exercitado sem travar as contas reais.
    alvo = "forca-bruta@exemplo.com"
    bruta = Sessao(base)
    for _ in range(5):
        _, html = bruta.get("/login")
        _, html = bruta.post("/login", {"email": alvo, "senha": "chute"}, token_de(html))
    checa("erros abaixo do limite só recusam", "E-mail ou senha incorretos" in html)

    _, html = bruta.get("/login")
    _, html = bruta.post("/login", {"email": alvo, "senha": "chute"}, token_de(html))
    checa("bloqueia depois do limite", "Muitas tentativas" in html)

    outra_conta = Sessao(base)
    html = outra_conta.entrar(email, senha)
    checa("bloqueio não afeta outra conta", "Painel" in html)

    if log is not None:
        secao("recuperação de senha")
        email3, _ = CONTA3
        nova = "senha-redefinida-pelo-smoke"

        reset = Sessao(base)
        _, html = reset.get("/senha/esqueci")
        _, html = reset.post("/senha/esqueci", {"email": email3}, token_de(html))
        checa("pedido é aceito", "enviamos as instruções" in html)

        _, html = reset.get("/senha/esqueci")
        _, html = reset.post(
            "/senha/esqueci", {"email": "ninguem@exemplo.com"}, token_de(html)
        )
        checa("e-mail inexistente dá a mesma resposta", "enviamos as instruções" in html)

        achado = re.search(r"(/senha/redefinir/[\w\-\.]+)", log.read_text())
        checa("link chega ao log quando não há SMTP", achado is not None)
        if achado:
            caminho = achado.group(1)
            codigo, _ = reset.get(caminho)
            checa("link abre o formulário", codigo == 200)

            _, html = reset.get(caminho)
            reset.post(
                caminho,
                {"nova_senha": nova, "confirmacao": nova},
                token_de(html),
            )

            depois = Sessao(base)
            html = depois.entrar(email3, nova)
            checa("senha nova funciona", "Painel" in html)

            _, html = reset.get(caminho)
            if "Link inválido" in html:
                checa("link é de uso único", True)
            else:
                _, html = reset.post(
                    caminho, {"nova_senha": nova, "confirmacao": nova}, token_de(html)
                )
                checa("link é de uso único", "Link inválido" in html)


# --------------------------------------------------------------------------


def main() -> int:
    """Interpreta os argumentos, roda as verificações e devolve o código de saída."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--url", help="Servidor já rodando. Sem isto, um é preparado.")
    parser.add_argument("--email", help="Conta de teste (exige --url).")
    parser.add_argument("--senha", help="Senha da conta de teste.")
    parser.add_argument("--email2", help="Segunda conta, para checar o isolamento.")
    parser.add_argument("--senha2", help="Senha da segunda conta.")
    args = parser.parse_args()

    if args.url and not (args.email and args.senha):
        parser.error("--url exige --email e --senha")

    encerrar = None
    log = None
    if args.url:
        base = args.url
        conta = (args.email, args.senha)
        conta2 = (args.email2, args.senha2) if args.email2 and args.senha2 else None
        if not conta2:
            print("aviso: sem --email2, o isolamento entre contas não será verificado")
        print("aviso: contra servidor externo, a recuperação de senha não é verificada")
    else:
        base, log, encerrar = preparar()
        conta, conta2 = CONTA, CONTA2

    try:
        verificar(base, conta, conta2, log)
    finally:
        if encerrar:
            encerrar()

    print()
    if falhas:
        print(f"FALHOU: {len(falhas)} verificação(ões)")
        for f in falhas:
            print(f"  - {f}")
        return 1

    print("tudo certo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
