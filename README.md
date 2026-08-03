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
flask seed                         # categorias padrão (opcional)

flask run --debug
```

Acesse http://127.0.0.1:5000.

## Estrutura

```
app/
├── __init__.py      # create_app(): monta o app e registra os blueprints
├── config.py        # presets development / testing / production
├── extensions.py    # db, migrate e csrf (sem app, evita import circular)
├── models.py        # Categoria e Lancamento
├── forms.py         # Flask-WTF, com campo de valor em formato brasileiro
├── services.py      # consultas e cálculos — a lógica de dinheiro fica aqui
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
| Categorias padrão | `flask seed` |
| Testes | `pytest` |
| Testes com cobertura | `pytest --cov=app` |
| Lint | `ruff check .` |

Todos assumem `FLASK_APP=run.py` exportado.

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

## Banco de dados

SQLite em `instance/app.db` por padrão. Para PostgreSQL, basta o `.env`:

```
DATABASE_URL=postgresql://usuario:senha@localhost:5432/rod_claude
```

SQLite tem suporte limitado a `NUMERIC` — para uso real, PostgreSQL é o
recomendado.

## Endpoints

| Rota | Descrição |
| --- | --- |
| `GET /` | Painel: saldo do mês, totais por categoria, evolução anual |
| `GET /health` | Status da aplicação e do banco (503 se o banco estiver fora) |
| `GET /lancamentos/` | Lista com filtros de período, tipo, categoria e busca |
| `GET,POST /lancamentos/novo` | Novo lançamento |
| `GET,POST /lancamentos/<id>/editar` | Edição |
| `POST /lancamentos/<id>/excluir` | Exclusão |
| `GET /categorias/` | Lista de categorias |
| `GET,POST /categorias/nova` | Nova categoria |
| `GET,POST /categorias/<id>/editar` | Edição |
| `POST /categorias/<id>/excluir` | Exclui ou desativa, se houver histórico |

## Ainda não implementado

- **Autenticação** — não há login; quem acessa a aplicação vê e altera tudo.
  Rode apenas localmente até isso existir.
- **Estorno** — lançamentos são editáveis e excluíveis. Auditoria financeira
  formal pediria lançamentos imutáveis com estorno por contra-lançamento.
- Contas a pagar/receber, recorrências e exportação para CSV/Excel.
