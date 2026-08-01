from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum

from app.extensions import db


def utcnow() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    """Colunas de auditoria compartilhadas pelos modelos."""

    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class TipoLancamento(StrEnum):
    RECEITA = "receita"
    DESPESA = "despesa"

    @property
    def rotulo(self) -> str:
        return "Receita" if self is TipoLancamento.RECEITA else "Despesa"


class Categoria(TimestampMixin, db.Model):
    __tablename__ = "categorias"
    __table_args__ = (db.UniqueConstraint("nome", "tipo", name="uq_categoria_nome_tipo"),)

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(60), nullable=False)
    tipo = db.Column(db.Enum(TipoLancamento, native_enum=False), nullable=False)

    # Categoria não se exclui quando já tem histórico: desativa-se, para não
    # quebrar os lançamentos antigos que apontam para ela.
    ativa = db.Column(db.Boolean, nullable=False, default=True)

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
