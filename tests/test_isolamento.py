"""Uma conta não pode ver nem tocar nos dados de outra.

É a garantia central do login: sem ela, autenticar serve só de porta de
entrada e qualquer usuário alcança tudo trocando o id na URL.
"""

from decimal import Decimal

from app import services
from app.models import Categoria, Lancamento, TipoLancamento


def test_listagem_nao_mostra_lancamento_alheio(logado, lancamentos, dados_do_outro):
    corpo = logado.get("/lancamentos/").get_data(as_text=True)

    assert "Salário de março" in corpo
    assert "Passagem aérea secreta" not in corpo


def test_painel_nao_soma_valor_alheio(logado, lancamentos, dados_do_outro):
    corpo = logado.get("/").get_data(as_text=True)

    # 2.500,00 é do outro usuário e não pode aparecer em nenhum total.
    assert "R$ 2.500,00" not in corpo


def test_categorias_do_outro_nao_aparecem(logado, categorias, dados_do_outro):
    corpo = logado.get("/categorias/").get_data(as_text=True)

    assert "Moradia" in corpo
    assert "Viagem" not in corpo


def test_editar_lancamento_alheio_da_404(logado, dados_do_outro):
    alvo = dados_do_outro["lancamento"]

    assert logado.get(f"/lancamentos/{alvo.id}/editar").status_code == 404


def test_excluir_lancamento_alheio_da_404_e_nao_apaga(logado, db, dados_do_outro):
    alvo_id = dados_do_outro["lancamento"].id

    resp = logado.post(f"/lancamentos/{alvo_id}/excluir")

    assert resp.status_code == 404
    assert db.session.get(Lancamento, alvo_id) is not None


def test_editar_categoria_alheia_da_404(logado, dados_do_outro):
    alvo = dados_do_outro["categoria"]

    assert logado.get(f"/categorias/{alvo.id}/editar").status_code == 404


def test_excluir_categoria_alheia_da_404_e_nao_apaga(logado, db, dados_do_outro):
    alvo_id = dados_do_outro["categoria"].id

    resp = logado.post(f"/categorias/{alvo_id}/excluir")

    assert resp.status_code == 404
    assert db.session.get(Categoria, alvo_id) is not None


def test_nao_da_para_lancar_em_categoria_alheia(logado, db, dados_do_outro):
    """O SelectField só oferece as próprias categorias; forçar o id deve falhar."""
    logado.post(
        "/lancamentos/novo",
        data={
            "descricao": "Tentativa",
            "valor": "10,00",
            "data": "2026-03-01",
            "categoria_id": str(dados_do_outro["categoria"].id),
        },
    )

    assert Lancamento.query.filter_by(descricao="Tentativa").count() == 0


def test_cada_conta_ve_o_proprio_resumo(app, usuario, outro_usuario, lancamentos, dados_do_outro):
    meu = services.calcular_resumo(usuario.id)
    dele = services.calcular_resumo(outro_usuario.id)

    assert meu.receitas == Decimal("5000.00")
    assert dele.receitas == Decimal("0.00")
    assert dele.despesas == Decimal("2500.00")


def test_mesmo_nome_de_categoria_em_contas_diferentes(db, usuario, outro_usuario):
    """Nome único por conta, não global: dois usuários podem ter 'Moradia'."""
    db.session.add_all(
        [
            Categoria(nome="Moradia", tipo=TipoLancamento.DESPESA, usuario_id=usuario.id),
            Categoria(nome="Moradia", tipo=TipoLancamento.DESPESA, usuario_id=outro_usuario.id),
        ]
    )
    db.session.commit()

    assert Categoria.query.filter_by(nome="Moradia").count() == 2


def test_busca_por_texto_nao_vaza(app, usuario, lancamentos, dados_do_outro):
    resultado = services.buscar_lancamentos(usuario.id, texto="passagem")

    assert resultado == []
