"""Consultas e cálculos do fluxo de caixa.

Isolar isso das rotas mantém as views curtas e deixa a lógica de dinheiro
testável sem precisar de requisição HTTP.

Toda função recebe `usuario_id` e filtra por ele: o isolamento entre contas
é feito aqui, num lugar só, em vez de espalhado pelas rotas.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func

from app.extensions import db
from app.models import Categoria, Lancamento, TipoLancamento

ZERO = Decimal("0.00")


@dataclass(frozen=True)
class Resumo:
    receitas: Decimal
    despesas: Decimal

    @property
    def saldo(self) -> Decimal:
        return self.receitas - self.despesas


@dataclass(frozen=True)
class TotalCategoria:
    categoria: str
    total: Decimal
    percentual: Decimal


def _aplica_periodo(query, inicio: date | None, fim: date | None):
    if inicio:
        query = query.filter(Lancamento.data >= inicio)
    if fim:
        query = query.filter(Lancamento.data <= fim)
    return query


def categorias_do_usuario(usuario_id: int, apenas_ativas: bool = False) -> list[Categoria]:
    query = Categoria.query.filter_by(usuario_id=usuario_id)
    if apenas_ativas:
        query = query.filter_by(ativa=True)
    return query.order_by(Categoria.tipo, Categoria.nome).all()


def calcular_resumo(
    usuario_id: int, inicio: date | None = None, fim: date | None = None
) -> Resumo:
    """Soma receitas e despesas do período. Ausência de lançamentos vira 0,00."""
    query = (
        db.session.query(Categoria.tipo, func.coalesce(func.sum(Lancamento.valor), 0))
        .join(Lancamento, Lancamento.categoria_id == Categoria.id)
        .filter(Lancamento.usuario_id == usuario_id)
        .group_by(Categoria.tipo)
    )
    totais = {tipo: Decimal(str(total)) for tipo, total in _aplica_periodo(query, inicio, fim)}

    return Resumo(
        receitas=totais.get(TipoLancamento.RECEITA, ZERO),
        despesas=totais.get(TipoLancamento.DESPESA, ZERO),
    )


def totais_por_categoria(
    usuario_id: int,
    tipo: TipoLancamento,
    inicio: date | None = None,
    fim: date | None = None,
) -> list[TotalCategoria]:
    """Totais agrupados por categoria, do maior para o menor."""
    query = (
        db.session.query(Categoria.nome, func.sum(Lancamento.valor).label("total"))
        .join(Lancamento, Lancamento.categoria_id == Categoria.id)
        .filter(Categoria.tipo == tipo, Lancamento.usuario_id == usuario_id)
        .group_by(Categoria.nome)
        .order_by(func.sum(Lancamento.valor).desc())
    )
    linhas = [(nome, Decimal(str(total))) for nome, total in _aplica_periodo(query, inicio, fim)]

    soma = sum((total for _, total in linhas), ZERO)
    return [
        TotalCategoria(
            categoria=nome,
            total=total,
            # Sem lançamentos não há divisão a fazer; evita ZeroDivisionError.
            percentual=(total / soma * 100).quantize(Decimal("0.1")) if soma else ZERO,
        )
        for nome, total in linhas
    ]


def buscar_lancamentos(
    usuario_id: int,
    inicio: date | None = None,
    fim: date | None = None,
    tipo: TipoLancamento | None = None,
    categoria_id: int | None = None,
    texto: str | None = None,
) -> list[Lancamento]:
    """Lista lançamentos aplicando os filtros informados, mais recentes primeiro."""
    query = Lancamento.query.join(Categoria).filter(Lancamento.usuario_id == usuario_id)

    query = _aplica_periodo(query, inicio, fim)
    if tipo:
        query = query.filter(Categoria.tipo == tipo)
    if categoria_id:
        query = query.filter(Lancamento.categoria_id == categoria_id)
    if texto:
        query = query.filter(Lancamento.descricao.ilike(f"%{texto}%"))

    return query.order_by(Lancamento.data.desc(), Lancamento.id.desc()).all()


def evolucao_mensal(usuario_id: int, ano: int) -> list[dict]:
    """Receitas, despesas e saldo mês a mês, para o gráfico do painel."""
    query = (
        db.session.query(
            func.strftime("%m", Lancamento.data).label("mes"),
            Categoria.tipo,
            func.sum(Lancamento.valor),
        )
        .join(Categoria, Lancamento.categoria_id == Categoria.id)
        .filter(
            func.strftime("%Y", Lancamento.data) == str(ano),
            Lancamento.usuario_id == usuario_id,
        )
        .group_by("mes", Categoria.tipo)
    )

    meses = {m: {"receitas": ZERO, "despesas": ZERO} for m in range(1, 13)}
    for mes, tipo, total in query:
        chave = "receitas" if tipo is TipoLancamento.RECEITA else "despesas"
        meses[int(mes)][chave] = Decimal(str(total))

    return [
        {
            "mes": mes,
            "receitas": valores["receitas"],
            "despesas": valores["despesas"],
            "saldo": valores["receitas"] - valores["despesas"],
        }
        for mes, valores in meses.items()
    ]
