from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum

from flask import current_app
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db


def utcnow() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    """Colunas de auditoria compartilhadas pelos modelos."""

    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class Usuario(TimestampMixin, UserMixin, db.Model):
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(180), nullable=False, unique=True, index=True)
    senha_hash = db.Column(db.String(255), nullable=False)
    ativo = db.Column(db.Boolean, nullable=False, default=True)

    categorias = db.relationship("Categoria", back_populates="usuario")
    lancamentos = db.relationship("Lancamento", back_populates="usuario")

    def __repr__(self) -> str:
        return f"<Usuario {self.email}>"

    def definir_senha(self, senha: str) -> None:
        """Guarda só o hash — nunca a senha.

        O algoritmo vem da config para os testes poderem usar um barato: o
        scrypt padrão é lento de propósito e domina o tempo da suíte.
        """
        metodo = current_app.config.get("PASSWORD_HASH_METHOD") if current_app else None
        self.senha_hash = (
            generate_password_hash(senha, method=metodo)
            if metodo
            else generate_password_hash(senha)
        )

    def conferir_senha(self, senha: str) -> bool:
        return check_password_hash(self.senha_hash, senha)

    @property
    def is_active(self) -> bool:
        """Flask-Login recusa o login de quem estiver desativado."""
        return self.ativo

    @staticmethod
    def normalizar_email(email: str) -> str:
        return email.strip().lower()


class TentativaAcesso(db.Model):
    """Registro de tentativas de login e de pedidos de redefinição.

    Serve para limitar força bruta. Guarda o e-mail *tentado*, exista ele ou
    não — contar só contas reais deixaria a varredura por e-mails livre.
    """

    __tablename__ = "tentativas_acesso"

    id = db.Column(db.Integer, primary_key=True)
    acao = db.Column(db.String(20), nullable=False)  # "login" ou "reset"
    identificador = db.Column(db.String(180), nullable=False, index=True)
    ip = db.Column(db.String(45), nullable=True, index=True)  # 45 cabe IPv6
    sucesso = db.Column(db.Boolean, nullable=False, default=False)
    criado_em = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False, index=True)

    def __repr__(self) -> str:
        return f"<TentativaAcesso {self.acao} {self.identificador} sucesso={self.sucesso}>"


class TipoLancamento(StrEnum):
    RECEITA = "receita"
    DESPESA = "despesa"

    @property
    def rotulo(self) -> str:
        return "Receita" if self is TipoLancamento.RECEITA else "Despesa"


class Categoria(TimestampMixin, db.Model):
    __tablename__ = "categorias"
    # O nome só precisa ser único dentro da conta de cada usuário.
    __table_args__ = (
        db.UniqueConstraint("usuario_id", "nome", "tipo", name="uq_categoria_nome_tipo"),
    )

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(60), nullable=False)
    tipo = db.Column(db.Enum(TipoLancamento, native_enum=False), nullable=False)

    # Categoria não se exclui quando já tem histórico: desativa-se, para não
    # quebrar os lançamentos antigos que apontam para ela.
    ativa = db.Column(db.Boolean, nullable=False, default=True)

    # Nullable no banco só para permitir a migração de dados já existentes;
    # a aplicação sempre preenche. Ver `flask criar-usuario`.
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True, index=True)
    usuario = db.relationship("Usuario", back_populates="categorias")

    lancamentos = db.relationship("Lancamento", back_populates="categoria")

    def __repr__(self) -> str:
        return f"<Categoria {self.nome} ({self.tipo})>"

    @property
    def em_uso(self) -> bool:
        return db.session.query(
            Lancamento.query.filter_by(categoria_id=self.id).exists()
        ).scalar()


class Lancamento(TimestampMixin, db.Model):
    __tablename__ = "lancamentos"
    __table_args__ = (db.CheckConstraint("valor > 0", name="ck_lancamento_valor_positivo"),)

    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.String(200), nullable=False)

    # Dinheiro nunca em float: Numeric preserva a precisão decimal exata.
    # O valor é sempre positivo; o sinal vem do tipo da categoria.
    valor = db.Column(db.Numeric(12, 2), nullable=False)

    data = db.Column(db.Date, nullable=False, default=date.today, index=True)
    observacao = db.Column(db.Text, nullable=True)

    categoria_id = db.Column(db.Integer, db.ForeignKey("categorias.id"), nullable=False)
    categoria = db.relationship("Categoria", back_populates="lancamentos")

    # Ver a nota em Categoria.usuario_id sobre o nullable.
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True, index=True)
    usuario = db.relationship("Usuario", back_populates="lancamentos")

    def __repr__(self) -> str:
        return f"<Lancamento {self.descricao} {self.valor}>"

    @property
    def tipo(self) -> TipoLancamento:
        """O tipo vem da categoria, então receita e despesa nunca divergem."""
        return self.categoria.tipo

    @property
    def valor_com_sinal(self) -> Decimal:
        """Negativo para despesa, positivo para receita. Útil em somas."""
        if self.tipo is TipoLancamento.DESPESA:
            return -self.valor
        return self.valor
