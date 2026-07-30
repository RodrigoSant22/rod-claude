def test_index_responde_ok(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Aplicação no ar" in resp.get_data(as_text=True)


def test_health_reporta_banco_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok", "database": "ok"}


def test_app_usa_config_de_teste(app):
    assert app.config["TESTING"] is True
    assert app.config["SQLALCHEMY_DATABASE_URI"] == "sqlite:///:memory:"
