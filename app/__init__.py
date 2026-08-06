"""Ponto de montagem da aplicação.

O app não é criado na importação deste módulo, e sim dentro de `create_app`.
Veja docs/flask-neste-projeto.md, seção "Application factory", para o porquê.
"""

from pathlib import Path

from dotenv import load_dotenv
from flask import Flask

from app import cli, filters
from app.config import Config, get_config
from app.extensions import csrf, db, login_manager, migrate

load_dotenv()


def create_app(config: str | type[Config] | None = None) -> Flask:
    """Application factory: monta e devolve uma instância do Flask.

    `config` aceita o nome de um preset ("development", "testing",
    "production") ou uma classe de configuração pronta.
    """
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config if isinstance(config, type) else get_config(config))

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    login_manager.init_app(app)

    filters.registrar(app)
    cli.registrar(app)

    from app.routes.auth import bp as auth_bp
    from app.routes.categorias import bp as categorias_bp
    from app.routes.lancamentos import bp as lancamentos_bp
    from app.routes.main import bp as main_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(lancamentos_bp)
    app.register_blueprint(categorias_bp)

    return app
