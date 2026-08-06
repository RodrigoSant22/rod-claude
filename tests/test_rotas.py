"""Rotas da aplicação: páginas, CRUD e comandos expostos."""

from decimal import Decimal

from app.models import Categoria, Lancamento, TipoLancamento


def test_health(client):
    resp = client.get("/health")

    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok", "database": "ok"}


def test_htmx_e_servido_localmente(logado):
    """O script é vendorizado: nada de CDN, e o caminho tem que existir."""
    corpo = logado.get("/").get_data(as_text=True)
    assert "/static/js/htmx.min.js" in corpo
    assert "unpkg.com" not in corpo

    resp = logado.get("/static/js/htmx.min.js")
    assert resp.status_code == 200
    assert len(resp.get_data()) > 40_000


def test_painel_abre_sem_dados(logado):
    resp = logado.get("/")

    assert resp.status_code == 200
    assert "Nenhum lançamento ainda" in resp.get_data(as_text=True)


def test_painel_mostra_valores_formatados(logado, lancamentos):
    corpo = logado.get("/").get_data(as_text=True)

    assert "R$" in corpo
    assert "Painel" in corpo


def test_listagem_mostra_todos(logado, lancamentos):
    corpo = logado.get("/lancamentos/").get_data(as_text=True)

    assert "Salário de março" in corpo
    assert "Cinema" in corpo


def test_listagem_filtra_por_texto(logado, lancamentos):
    corpo = logado.get("/lancamentos/?texto=cinema").get_data(as_text=True)

    assert "Cinema" in corpo
    assert "Salário de março" not in corpo


def test_listagem_filtra_por_periodo(logado, lancamentos):
    corpo = logado.get("/lancamentos/?inicio=2026-04-01&fim=2026-04-30").get_data(as_text=True)

    assert "Cinema" not in corpo


def test_filtro_com_data_invalida_nao_quebra(logado, lancamentos):
    resp = logado.get("/lancamentos/?inicio=nao-e-data")

    assert resp.status_code == 200


def test_htmx_recebe_so_o_fragmento(logado, lancamentos):
    resp = logado.get("/lancamentos/", headers={"HX-Request": "true"})
    corpo = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert '<div id="tabela">' in corpo
    assert "<html" not in corpo  # sem o layout completo


def test_criar_lancamento(logado, db, usuario, categorias):
    resp = logado.post(
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
    assert criado.usuario_id == usuario.id


def test_criar_com_valor_invalido_nao_persiste(logado, db, categorias):
    logado.post(
        "/lancamentos/novo",
        data={
            "descricao": "Inválido",
            "valor": "0,00",
            "data": "2026-03-20",
            "categoria_id": str(categorias["moradia"].id),
        },
    )

    assert Lancamento.query.filter_by(descricao="Inválido").count() == 0


def test_criar_sem_categoria_redireciona_para_cadastro(logado, db):
    resp = logado.get("/lancamentos/novo", follow_redirects=True)

    assert "Nova categoria" in resp.get_data(as_text=True)


def test_editar_lancamento(logado, db, lancamentos, categorias):
    alvo = lancamentos[2]

    logado.post(
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


def test_excluir_lancamento(logado, db, lancamentos):
    alvo_id = lancamentos[2].id

    logado.post(f"/lancamentos/{alvo_id}/excluir", follow_redirects=True)

    assert db.session.get(Lancamento, alvo_id) is None


def test_excluir_via_htmx_devolve_a_tabela(logado, db, lancamentos):
    alvo_id = lancamentos[2].id

    resp = logado.post(f"/lancamentos/{alvo_id}/excluir", headers={"HX-Request": "true"})

    assert resp.status_code == 200
    assert '<div id="tabela">' in resp.get_data(as_text=True)
    assert db.session.get(Lancamento, alvo_id) is None


def test_lancamento_inexistente_da_404(logado):
    assert logado.get("/lancamentos/999/editar").status_code == 404


def test_criar_categoria(logado, db, usuario):
    logado.post(
        "/categorias/nova",
        data={"nome": "Pets", "tipo": "despesa", "ativa": "y"},
        follow_redirects=True,
    )

    criada = Categoria.query.filter_by(nome="Pets").one()
    assert criada.usuario_id == usuario.id


def test_categoria_duplicada_e_recusada(logado, db, categorias):
    resp = logado.post(
        "/categorias/nova",
        data={"nome": "Moradia", "tipo": "despesa", "ativa": "y"},
        follow_redirects=True,
    )

    assert "Já existe" in resp.get_data(as_text=True)
    assert Categoria.query.filter_by(nome="Moradia").count() == 1


def test_categoria_em_uso_e_desativada_nao_excluida(logado, db, categorias, lancamentos):
    alvo = categorias["moradia"]

    resp = logado.post(f"/categorias/{alvo.id}/excluir", follow_redirects=True)

    assert "desativada" in resp.get_data(as_text=True)
    assert db.session.get(Categoria, alvo.id) is not None
    assert db.session.get(Categoria, alvo.id).ativa is False


def test_categoria_sem_uso_e_excluida(logado, db, categorias):
    alvo = categorias["lazer"]

    logado.post(f"/categorias/{alvo.id}/excluir", follow_redirects=True)

    assert db.session.get(Categoria, alvo.id) is None


def test_categoria_inativa_nao_aparece_no_formulario(logado, db, categorias):
    categorias["lazer"].ativa = False
    db.session.commit()

    corpo = logado.get("/lancamentos/novo").get_data(as_text=True)

    assert "Lazer" not in corpo
    assert "Moradia" in corpo


def test_seed_cria_categorias_padrao(app, db, usuario):
    runner = app.test_cli_runner()

    resultado = runner.invoke(args=["seed", "--email", usuario.email])

    assert "categoria(s) criada(s)" in resultado.output
    assert (
        Categoria.query.filter_by(
            tipo=TipoLancamento.RECEITA, usuario_id=usuario.id
        ).count()
        >= 4
    )


def test_seed_e_idempotente(app, db, usuario):
    runner = app.test_cli_runner()

    runner.invoke(args=["seed", "--email", usuario.email])
    total = Categoria.query.count()
    runner.invoke(args=["seed", "--email", usuario.email])

    assert Categoria.query.count() == total


def test_seed_sem_conta_avisa(app, db):
    runner = app.test_cli_runner()

    resultado = runner.invoke(args=["seed"])

    assert "flask criar-usuario" in resultado.output


def test_seed_usa_a_unica_conta_quando_ha_so_uma(app, db, usuario):
    runner = app.test_cli_runner()

    resultado = runner.invoke(args=["seed"])

    assert usuario.email in resultado.output
