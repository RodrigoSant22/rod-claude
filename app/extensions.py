"""Instâncias das extensões, criadas sem app para evitar import circular.

Cada uma é ligada ao app dentro de `create_app()` via `init_app()`.
"""

from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
migrate = Migrate()

# Habilita `csrf_token()` nos templates e protege todo POST por padrão.
csrf = CSRFProtect()

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Faça login para continuar."
login_manager.login_message_category = "aviso"
# Invalida a sessão se o identificador do navegador mudar.
login_manager.session_protection = "strong"


@login_manager.user_loader
def carregar_usuario(usuario_id: str):
    from app.models import Usuario

    return db.session.get(Usuario, int(usuario_id))
