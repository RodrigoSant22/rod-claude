"""Instâncias das extensões, criadas sem app para evitar import circular.

Cada uma é ligada ao app dentro de `create_app()` via `init_app()`.
"""

from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
migrate = Migrate()

# Habilita `csrf_token()` nos templates e protege todo POST por padrão.
csrf = CSRFProtect()
