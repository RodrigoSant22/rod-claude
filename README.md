# rod-claude — Fluxo de Caixa

Controle de receitas e despesas em Flask (Python 3.11+): lançamentos por
categoria, filtros, saldo do mês e evolução anual.

## Rodando localmente

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

cp .env.example .env               # ajuste SECRET_KEY

export FLASK_APP=run.py            # Windows: set FLASK_APP=run.py
flask db upgrade                   # cria o banco
flask criar-usuario                # sua conta de acesso
flask seed                         # categorias padrão (opcional)

flask run --debug
```

Acesse http://127.0.0.1:5000 e entre com o e-mail e a senha que você definiu.

> **Atualizando de uma versão sem login?** Rode `flask db upgrade` e depois
> `flask criar-usuario`. Seus lançamentos e categorias existentes são
> atribuídos automaticamente à primeira conta criada — nada se perde.

## Estrutura

```
app/
├── __init__.py      # create_app(): monta o app e registra os blueprints
├── config.py        # presets development / testing / production
├── extensions.py    # db, migrate e csrf (sem app, evita import circular)
├── models.py        # Usuario, Categoria e Lancamento
├── forms.py         # Flask-WTF, com campo de valor em formato brasileiro
├── services.py      # consultas e cálculos — a lógica de dinheiro fica aqui
├── exportacao.py    # geração de CSV e XLSX
├── seguranca.py     # freio de força bruta
├── tokens.py        # links assinados de redefinição de senha
├── mailer.py        # envio por SMTP, com queda para o log
├── filters.py       # formatação de moeda e data para o Jinja
├── cli.py           # comandos init-db e seed
├── routes/          # um blueprint por área
├── templates/
└── static/
migrations/          # Alembic
tests/               # pytest
```

## Comandos

| Ação | Comando |
| --- | --- |
| Servidor de desenvolvimento | `flask run --debug` |
| Criar/atualizar o banco | `flask db upgrade` |
| Nova migração após mudar models | `flask db migrate -m "descrição"` |
| Criar conta de acesso | `flask criar-usuario` |
| Categorias padrão | `flask seed` (ou `--email`, se houver mais de uma conta) |
| Testes | `pytest` |
| Testes com cobertura | `pytest --cov=app` |
| Teste de fumaça | `python scripts/smoke.py` |
| Lint | `ruff check .` |

Todos assumem `FLASK_APP=run.py` exportado.

## As três camadas de verificação

| | O que responde | Executa o código? |
| --- | --- | --- |
| `ruff check .` | O código está bem escrito? | Não, só lê |
| `pytest` | A lógica está correta? | Sim, em pedaços isolados |
| `python scripts/smoke.py` | O sistema funciona de verdade? | Sim, servidor real por HTTP |

O smoke existe por um motivo específico: para ganhar velocidade, o
`TestingConfig` **desliga o CSRF** e troca o hash de senha por um barato.
Cada `= False` ali é um pedaço do sistema que o pytest deixa de exercitar.
O smoke sobe o servidor com a configuração de desenvolvimento, sem nada
desligado, e conversa com ele por HTTP como um navegador faria.

Ele já pegou uma regressão real: com valor `0,00`, o formulário respondia
"informe o valor" em vez de "deve ser maior que zero" — porque
`Decimal("0.00")` é falsy e o `DataRequired` disparava antes do
`NumberRange`. O pytest passava, já que a lista de erros não estava vazia.

Sem argumentos, o script prepara um banco temporário, cria duas contas,
sobe o servidor numa porta livre, roda as verificações e limpa tudo no fim.
Para apontá-lo a um servidor que já está no ar:

```bash
python scripts/smoke.py --url http://127.0.0.1:5000 \
    --email eu@exemplo.com --senha minha-senha
```

## Decisões de projeto

**Dinheiro em `Numeric`, nunca `float`.** `0.1 + 0.2` em ponto flutuante dá
`0.30000000000000004`; somado ao longo de milhares de lançamentos, o saldo não
fecha. Os valores são `Numeric(12, 2)` no banco e `Decimal` no Python, e há
teste garantindo isso.

**O valor é sempre positivo.** Receita ou despesa vem do tipo da categoria, o
que impede um lançamento de contradizer a própria categoria. A propriedade
`Lancamento.valor_com_sinal` aplica o sinal quando é preciso somar.

**Categoria com histórico não se exclui.** Ao tentar excluir uma categoria que
já tem lançamentos, o sistema a desativa — apagar levaria o histórico junto.
Categorias inativas somem do formulário mas continuam nos relatórios.

**HTMX é opcional e local.** Os filtros e a exclusão usam HTMX para atualizar
só a tabela, mas tudo é `<form>` HTML comum por baixo: sem JavaScript, a
aplicação continua funcionando com recarga de página. O script está
vendorizado em `app/static/js/htmx.min.js` (versão 2.0.10, estável), então não
há dependência de CDN nem de rede externa.

Para atualizar a versão, baixe de https://htmx.org/docs/#installing e
substitua o arquivo. A linha 4.x está em beta e usa outra API — não troque sem
revisar os atributos `hx-*` dos templates.

**Cálculos fora das rotas.** `services.py` concentra as consultas, então a
lógica de dinheiro é testável sem subir requisição HTTP.

**Isolamento por conta feito num lugar só.** Toda função de `services.py`
recebe `usuario_id` e filtra por ele, em vez de cada rota lembrar de filtrar.
Buscas por id (editar, excluir) usam `filter_by(id=..., usuario_id=...)` e
respondem **404** — não 403 — para registro de outra conta: um 403
confirmaria que aquele id existe.

**Não há cadastro pela web.** Contas são criadas com `flask criar-usuario`.
Num sistema financeiro, formulário aberto de registro é porta de entrada sem
necessidade. A senha é guardada como hash `scrypt` (padrão do Werkzeug).

**Freio de força bruta contado no banco.** A tabela `tentativas_acesso`
registra cada falha, com duas contagens em paralelo: por conta (5 erros em
15 min) e por IP (20 no mesmo período). O limite por IP é mais alto de
propósito — ele existe para conter varredura de vários e-mails, não para
atrapalhar quem divide a mesma rede. As tentativas contam o e-mail
*digitado*, exista ele ou não: contar só contas reais deixaria a enumeração
de endereços livre. Acertar a senha zera o contador da conta.

**Link de redefinição sem tabela de tokens.** O token é assinado com o
`SECRET_KEY` e embute uma impressão do hash da senha atual. Isso o torna de
uso único sem guardar estado: trocada a senha, o hash muda e qualquer link
antigo — inclusive um que tenha vazado — deixa de valer. A validade é de 1
hora.

**CSV feito para o Excel em português.** Separador `;` e UTF-8 com BOM.
Com vírgula, o duplo clique no Brasil joga tudo numa coluna só; sem o BOM,
os acentos chegam quebrados. Os valores usam vírgula decimal, senão o Excel
os trata como texto e não soma.

**O valor exportado sai com sinal** — negativo para despesa. Uma coluna
numérica só permite `SOMA()` direto e funciona em tabela dinâmica; duas
colunas separadas obrigariam a subtrair uma da outra a cada análise. A
coluna `Tipo` continua lá para filtrar.

**O XLSX grava tipos, não texto.** Datas como data e valores como número,
com formato de moeda aplicado — do contrário a planilha não somaria nem
ordenaria corretamente. Vem com cabeçalho congelado, filtro ligado e uma
aba `Resumo` com totais e quebra por categoria.

**Sem SMTP, o link vai para o log.** É o que torna a recuperação de senha
utilizável numa instalação local: o link aparece no terminal do `flask run`.
Configure `MAIL_SERVER` e companhia no `.env` para enviar de verdade.

## Banco de dados

SQLite em `instance/app.db` por padrão. Para PostgreSQL, basta o `.env`:

```
DATABASE_URL=postgresql://usuario:senha@localhost:5432/rod_claude
```

SQLite tem suporte limitado a `NUMERIC` — para uso real, PostgreSQL é o
recomendado.

## Endpoints

Tudo exige login, exceto `/login` e `/health`.

| Rota | Descrição |
| --- | --- |
| `GET,POST /login` | Entrada |
| `POST /logout` | Saída |
| `GET,POST /senha/esqueci` | Pedir link de redefinição |
| `GET,POST /senha/redefinir/<token>` | Escolher nova senha pelo link |
| `GET,POST /conta/senha` | Alterar a própria senha |
| `GET /` | Painel: saldo do mês, totais por categoria, evolução anual |
| `GET /health` | Status da aplicação e do banco (503 se o banco estiver fora) |
| `GET /lancamentos/` | Lista com filtros de período, tipo, categoria e busca |
| `GET /lancamentos/exportar.csv` | Exporta em CSV, com os mesmos filtros |
| `GET /lancamentos/exportar.xlsx` | Exporta em Excel, com os mesmos filtros |
| `GET,POST /lancamentos/novo` | Novo lançamento |
| `GET,POST /lancamentos/<id>/editar` | Edição |
| `POST /lancamentos/<id>/excluir` | Exclusão |
| `GET /categorias/` | Lista de categorias |
| `GET,POST /categorias/nova` | Nova categoria |
| `GET,POST /categorias/<id>/editar` | Edição |
| `POST /categorias/<id>/excluir` | Exclui ou desativa, se houver histórico |

## Manutenção

A tabela `tentativas_acesso` cresce com o uso. Para descartar o que já
passou da validade:

```bash
flask limpar-tentativas            # remove o que tem mais de 30 dias
flask limpar-tentativas --dias 7
```

## Ainda não implementado

- **Estorno** — lançamentos são editáveis e excluíveis. Auditoria financeira
  formal pediria lançamentos imutáveis com estorno por contra-lançamento.
- Contas a pagar/receber e recorrências.
- A exportação monta o arquivo inteiro em memória. Para dezenas de milhares
  de lançamentos, valeria trocar por escrita em fluxo.

Antes de expor a aplicação na internet:

- defina um `SECRET_KEY` próprio (ele assina as sessões *e* os links de
  redefinição de senha);
- use `FLASK_ENV=production`, que exige HTTPS nos cookies;
- configure SMTP, senão a recuperação de senha só funciona para quem tem
  acesso ao log do servidor;
- se houver proxy reverso na frente, configure o `ProxyFix` do Werkzeug —
  sem isso o `remote_addr` é o do proxy, e o limite por IP passa a valer
  para todos os visitantes somados.
