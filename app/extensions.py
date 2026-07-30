"""Instâncias das extensões, criadas sem app para evitar import circular.

Cada uma é ligada ao app dentro de `create_app()` via `init_app()`.
"""

from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
migrate = Migrate()
