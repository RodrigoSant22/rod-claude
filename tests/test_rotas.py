from decimal import Decimal

from app.models import Categoria, Lancamento, TipoLancamento


def test_health(client):
    resp = client.get("/health")

    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok", "database": "ok"}


def test_painel_abre_sem_dados(client):
    resp = client.get("/")

    assert resp.status_code == 200
    assert "Nenhum lançamento ainda" in resp.get_data(as_text=True)


def test_painel_mostra_valores_formatados(client, lancamentos):
    corpo = client.get("/").get_data(as_text=True)

    assert "R$" in corpo
    assert "Painel" in corpo


def test_listagem_mostra_todos(client, lancamentos):
    corpo = client.get("/lancamentos/").get_data(as_text=True)

    assert "Salário de março" in corpo
    assert "Cinema" in corpo


def test_listagem_filtra_por_texto(client, lancamentos):
    corpo = client.get("/lancamentos/?texto=cinema").get_data(as_text=True)

    assert "Cinema" in corpo
    assert "Salário de março" not in corpo


def test_listagem_filtra_por_periodo(client, lancamentos):
    corpo = client.get(
        "/lancamentos/?inicio=2026-04-01&fim=2026-04-30"
    ).get_data(as_text=True)

    assert "Cinema" not in corpo


def test_filtro_com_data_invalida_nao_quebra(client, lancamentos):
    resp = client.get("/lancamentos/?inicio=nao-e-data")

    assert resp.status_code == 200


def test_htmx_recebe_so_o_fragmento(client, lancamentos):
    resp = client.get("/lancamentos/", headers={"HX-Request": "true"})
    corpo = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert '<div id="tabela">' in corpo
    assert "<html" not in corpo  # sem o layout completo


def test_criar_lancamento(client, db, categorias):
    resp = client.post(
        "/lancamentos/novo",
        data={
            "descricao": "Mercado",
            "valor": "250,75",
            "data": "2026-03-20",
            "categoria_id": str(categorias["moradia"].id),
        },
        follow_redirects=True,
    )

    assert resp.status_code == 200

    criado = Lancamento.query.filter_by(descricao="Mercado").one()
    assert criado.valor == Decimal("250.75")


def test_criar_com_valor_invalido_nao_persiste(client, db, categorias):
    client.post(
        "/lancamentos/novo",
        data={
            "descricao": "Inválido",
            "valor": "0,00",
            "data": "2026-03-20",
            "categoria_id": str(categorias["moradia"].id),
        },
    )

    assert Lancamento.query.filter_by(descricao="Inválido").count() == 0


def test_criar_sem_categoria_redireciona_para_cadastro(client, db):
    resp = client.get("/lancamentos/novo", follow_redirects=True)

    assert "Nova categoria" in resp.get_data(as_text=True)


def test_editar_lancamento(client, db, lancamentos, categorias):
    alvo = lancamentos[2]

    client.post(
        f"/lancamentos/{alvo.id}/editar",
        data={
            "descricao": "Cinema com pipoca",
            "valor": "80,00",
            "data": "2026-03-15",
            "categoria_id": str(categorias["lazer"].id),
        },
        follow_redirects=True,
    )

    atualizado = db.session.get(Lancamento, alvo.id)
    assert atualizado.descricao == "Cinema com pipoca"
    assert atualizado.valor == Decimal("80.00")


def test_excluir_lancamento(client, db, lancamentos):
    alvo_id = lancamentos[2].id

    client.post(f"/lancamentos/{alvo_id}/excluir", follow_redirects=True)

    assert db.session.get(Lancamento, alvo_id) is None


def test_excluir_via_htmx_devolve_a_tabela(client, db, lancamentos):
    alvo_id = lancamentos[2].id

    resp = client.post(
        f"/lancamentos/{alvo_id}/excluir", headers={"HX-Request": "true"}
    )

    assert resp.status_code == 200
    assert '<div id="tabela">' in resp.get_data(as_text=True)
    assert db.session.get(Lancamento, alvo_id) is None


def test_lancamento_inexistente_da_404(client):
    assert client.get("/lancamentos/999/editar").status_code == 404


def test_criar_categoria(client, db):
    client.post(
        "/categorias/nova",
        data={"nome": "Pets", "tipo": "despesa", "ativa": "y"},
        follow_redirects=True,
    )

    assert Categoria.query.filter_by(nome="Pets").count() == 1


def test_categoria_duplicada_e_recusada(client, db, categorias):
    resp = client.post(
        "/categorias/nova",
        data={"nome": "Moradia", "tipo": "despesa", "ativa": "y"},
        follow_redirects=True,
    )

    assert "Já existe" in resp.get_data(as_text=True)
    assert Categoria.query.filter_by(nome="Moradia").count() == 1


def test_categoria_em_uso_e_desativada_nao_excluida(client, db, categorias, lancamentos):
    alvo = categorias["moradia"]

    resp = client.post(f"/categorias/{alvo.id}/excluir", follow_redirects=True)

    assert "desativada" in resp.get_data(as_text=True)
    assert db.session.get(Categoria, alvo.id) is not None
    assert db.session.get(Categoria, alvo.id).ativa is False


def test_categoria_sem_uso_e_excluida(client, db, categorias):
    alvo = categorias["lazer"]

    client.post(f"/categorias/{alvo.id}/excluir", follow_redirects=True)

    assert db.session.get(Categoria, alvo.id) is None


def test_categoria_inativa_nao_aparece_no_formulario(client, db, categorias):
    categorias["lazer"].ativa = False
    db.session.commit()

    corpo = client.get("/lancamentos/novo").get_data(as_text=True)

    assert "Lazer" not in corpo
    assert "Moradia" in corpo


def test_seed_cria_categorias_padrao(app, db):
    runner = app.test_cli_runner()

    resultado = runner.invoke(args=["seed"])

    assert "categoria(s) criada(s)" in resultado.output
    assert Categoria.query.filter_by(tipo=TipoLancamento.RECEITA).count() >= 4


def test_seed_e_idempotente(app, db):
    runner = app.test_cli_runner()

    runner.invoke(args=["seed"])
    total = Categoria.query.count()
    runner.invoke(args=["seed"])

    assert Categoria.query.count() == total
