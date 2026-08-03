import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-inseguro-troque-em-producao")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'app.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # O cookie de sessão guarda o login: fora do alcance de JavaScript e
    # não enviado em requisições vindas de outro site.
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_DURATION = timedelta(days=14)

    # Freio de força bruta. O limite por IP é mais alto que o por conta:
    # ele existe para conter varredura de vários e-mails, não uso legítimo
    # de quem divide a mesma rede.
    LOGIN_MAX_POR_CONTA = 5
    LOGIN_MAX_POR_IP = 20
    LOGIN_JANELA = timedelta(minutes=15)

    RESET_MAX_POR_CONTA = 3
    RESET_MAX_POR_IP = 10
    RESET_JANELA = timedelta(minutes=60)

    # Validade do link de redefinição de senha.
    RESET_TOKEN_VALIDADE = timedelta(hours=1)

    # SMTP. Sem MAIL_SERVER definido, o link é escrito no log em vez de
    # enviado — é o que permite usar a recuperação de senha localmente.
    MAIL_SERVER = os.environ.get("MAIL_SERVER")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", "587"))
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").lower() != "false"
    MAIL_FROM = os.environ.get("MAIL_FROM", "nao-responda@localhost")


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False

    # Hash barato só nos testes: o scrypt padrão levava a suíte de 1s a 20s.
    # Nunca usar isto fora daqui.
    PASSWORD_HASH_METHOD = "pbkdf2:sha256:1"


class ProductionConfig(Config):
    # Exige HTTPS para transmitir os cookies de sessão.
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True


configs = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(name: str | None = None) -> type[Config]:
    """Resolve a classe de configuração pelo nome ou pela variável FLASK_ENV."""
    name = name or os.environ.get("FLASK_ENV", "development")
    return configs.get(name, DevelopmentConfig)
