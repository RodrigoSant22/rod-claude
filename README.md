# rod-claude

Aplicação web em Flask (Python 3.11+), organizada com *application factory* e blueprints.

## Rodando localmente

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

cp .env.example .env               # ajuste SECRET_KEY

flask --app run.py run --debug     # ou: python run.py
```

Acesse http://127.0.0.1:5000.

## Estrutura

```
app/
├── __init__.py      # create_app(): monta o app e registra os blueprints
├── config.py        # presets development / testing / production
├── extensions.py    # instâncias de db e migrate (sem app, evita import circular)
├── models.py        # modelos e mixins do SQLAlchemy
├── routes/          # um blueprint por área da aplicação
├── templates/       # Jinja2
└── static/
tests/               # pytest, com fixtures em conftest.py
run.py               # ponto de entrada
```

## Comandos

| Ação | Comando |
| --- | --- |
| Servidor de desenvolvimento | `flask --app run.py run --debug` |
| Testes | `pytest` |
| Testes com cobertura | `pytest --cov=app` |
| Lint | `ruff check .` |
| Corrigir lint | `ruff check --fix .` |

## Banco de dados

Por padrão SQLite em `instance/app.db`. Para trocar, defina `DATABASE_URL` no `.env`.

Migrações com Flask-Migrate:

```bash
flask --app run.py db init          # só na primeira vez
flask --app run.py db migrate -m "descrição"
flask --app run.py db upgrade
```

## Endpoints

| Rota | Descrição |
| --- | --- |
| `GET /` | Página inicial |
| `GET /health` | Status da aplicação e do banco (503 se o banco estiver fora) |
