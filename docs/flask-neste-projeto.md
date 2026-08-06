# Flask neste projeto

Guia dos mecanismos do Flask usando o código deste repositório como exemplo.
Não é um tutorial genérico: cada seção aponta para o arquivo onde a coisa
acontece de verdade.

- [O ciclo de uma requisição](#o-ciclo-de-uma-requisição)
- [Application factory](#application-factory)
- [Extensões e o padrão init_app](#extensões-e-o-padrão-init_app)
- [Os contextos e os proxies](#os-contextos-e-os-proxies)
- [Blueprints](#blueprints)
- [Rotas e respostas](#rotas-e-respostas)
- [before_request](#before_request)
- [Jinja](#jinja)
- [Formulários e CSRF](#formulários-e-csrf)
- [Login](#login)
- [Banco de dados](#banco-de-dados)
- [Migrações](#migrações)
- [Configuração](#configuração)
- [Comandos de linha](#comandos-de-linha)
- [Testes](#testes)

---

## O ciclo de uma requisição

Do clique ao HTML, no caso de `GET /lancamentos/?texto=cinema`:

```
navegador
   │ GET /lancamentos/?texto=cinema
   ▼
servidor WSGI (flask run em desenvolvimento)
   │ cria o request context
   ▼
before_request do blueprint        app/routes/lancamentos.py :: exigir_login
   │ (login_required — segue ou desvia para /login)
   ▼
função da rota                     app/routes/lancamentos.py :: listar
   │ lê request.args, chama services
   ▼
services                           app/services.py :: buscar_lancamentos
   │ monta e executa a query
   ▼
render_template                    app/templates/lancamentos/listar.html
   │ Jinja monta o HTML
   ▼
Response  ──▶  navegador
```

O ponto a reter: **o Flask não chama sua função direto**. Ele monta um
contexto em volta dela, executa os ganchos registrados, e só então entrega a
requisição à rota. Quase toda a "mágica" do Flask está nesse envelope.

---

## Application factory

`app/__init__.py` não cria o app na importação do módulo. Cria dentro de uma
função:

```python
def create_app(config=None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(...)
    ...
    return app
```

O caminho ingênuo seria `app = Flask(__name__)` no topo do arquivo. Funciona
em exemplos de uma página e cria três problemas depois:

1. **Testes** — cada teste quer um app novo, com configuração própria e banco
   limpo. Com o app global, você tem um só, compartilhado, contaminado pelo
   teste anterior. É a factory que permite `create_app(TestingConfig)` em
   `tests/conftest.py`.
2. **Importação circular** — as rotas precisam do `app` para se registrar, e o
   `app` precisa das rotas. Com a factory, os `import` das rotas ficam *dentro*
   da função, executados depois de o app existir.
3. **Configuração** — dá para criar o mesmo app com config de desenvolvimento,
   de teste ou de produção sem variável de ambiente global.

Repare que os imports dos blueprints estão dentro de `create_app`, e não no
topo. Não é desleixo — é o que quebra o ciclo do item 2.

`instance_relative_config=True` cria a pasta `instance/`, onde o SQLite mora.
Ela fica fora do controle de versão de propósito: é dado, não código.

---

## Extensões e o padrão init_app

`app/extensions.py` cria as extensões **sem** app:

```python
db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()
login_manager = LoginManager()
```

E `create_app` as amarra:

```python
db.init_app(app)
migrate.init_app(app, db)
csrf.init_app(app)
login_manager.init_app(app)
```

Por que separar? Porque `app/models.py` precisa de `db` para declarar as
colunas, e `create_app` precisa de `models` para as migrações enxergarem as
tabelas. Se `db` nascesse dentro de `create_app`, o ciclo seria inescapável.
Com `db` num módulo neutro, qualquer um importa sem depender do app.

O preço é que `db` fica "solto" até alguém chamar `init_app`. Usar `db.session`
fora de um contexto de aplicação levanta erro — o que nos leva à próxima seção.

---

## Os contextos e os proxies

Esta é a parte do Flask que mais estranha quem vem de outros frameworks.

`current_app`, `request`, `session` e `g` são importados como se fossem
objetos globais:

```python
from flask import current_app, request
```

Mas não são. São **proxies**: objetos que, a cada acesso, procuram o valor real
associado à requisição que está sendo atendida *naquela thread*. Duas
requisições simultâneas veem `request` diferentes, apesar de o nome importado
ser o mesmo.

Existem dois contextos:

| Contexto | O que dá acesso | Quando existe |
| --- | --- | --- |
| **Application context** | `current_app`, `g` | Durante uma requisição, um comando CLI, ou dentro de `with app.app_context()` |
| **Request context** | `request`, `session` | Só durante uma requisição HTTP |

Onde isso aparece no projeto:

**`app/seguranca.py`** lê a política de limites do `current_app.config` em vez
de receber por parâmetro — assim a mesma função serve a qualquer app, com
qualquer configuração:

```python
limite_conta = current_app.config[chave_conta]
```

**`app/models.py`** faz o mesmo em `definir_senha`, mas com uma guarda:

```python
metodo = current_app.config.get("PASSWORD_HASH_METHOD") if current_app else None
```

O `if current_app` existe porque o método pode ser chamado fora de qualquer
contexto — e o proxy sabe responder que está vazio em vez de estourar.

**`tests/conftest.py`** cria o contexto na mão, já que não há requisição HTTP:

```python
with app.app_context():
    _db.create_all()
    yield app
```

Sem esse `with`, qualquer `db.session` no teste falharia com
*"Working outside of application context"* — a mensagem de erro mais comum de
quem começa em Flask.

---

## Blueprints

Um blueprint é um conjunto de rotas que se registra no app depois. Cada área
do sistema tem o seu:

| Arquivo | Blueprint | Prefixo |
| --- | --- | --- |
| `app/routes/main.py` | `main` | (nenhum) |
| `app/routes/auth.py` | `auth` | (nenhum) |
| `app/routes/lancamentos.py` | `lancamentos` | `/lancamentos` |
| `app/routes/categorias.py` | `categorias` | `/categorias` |

```python
bp = Blueprint("lancamentos", __name__, url_prefix="/lancamentos")

@bp.get("/")
def listar():
    ...
```

O `url_prefix` evita repetir `/lancamentos` em cada rota.

O nome do blueprint vira **namespace** no `url_for`:

```python
url_for("lancamentos.listar")     # /lancamentos/
url_for("categorias.listar")      # /categorias/
```

Por isso há duas funções chamadas `listar` no projeto sem conflito.

Nunca escreva a URL na mão no template. Com `url_for`, mudar o `url_prefix`
conserta todos os links sozinho; com `"/lancamentos/"` escrito à mão, você
caça string por string.

---

## Rotas e respostas

O Flask aceita vários tipos de retorno e converte para `Response`:

```python
return render_template("index.html")          # str  → HTML
return {"status": "ok"}                       # dict → JSON
return {"status": "degraded"}, 503            # tupla → JSON + status
return redirect(url_for("main.index"))        # Response pronto
```

Os três primeiros estão em `app/routes/main.py`: `index` devolve HTML e
`health` devolve dicionário — que o Flask serializa em JSON automaticamente,
sem `jsonify` explícito.

Quando é preciso controlar cabeçalhos, monta-se o `Response` à mão. É o caso da
exportação, em `app/routes/lancamentos.py`:

```python
return Response(
    conteudo,
    mimetype=tipo_mime,
    headers={"Content-Disposition": "attachment; filename=..."},
)
```

O `Content-Disposition: attachment` é o que faz o navegador **baixar** em vez de
tentar exibir.

### Decoradores de rota

```python
@bp.get("/")                                  # só GET
@bp.post("/<int:lancamento_id>/excluir")      # só POST
@bp.route("/novo", methods=["GET", "POST"])   # ambos
```

O `<int:lancamento_id>` captura o trecho da URL, converte para `int` e passa
como argumento. Se vier `/lancamentos/abc/editar`, o Flask devolve 404 antes de
chamar sua função — a conversão é a validação.

### flash

`flash("Lançamento registrado.", "sucesso")` guarda a mensagem na sessão para a
**próxima** requisição. É o que permite avisar depois de um redirecionamento —
o padrão POST/Redirect/GET, que evita reenvio do formulário ao atualizar a
página. O `base.html` consome com `get_flashed_messages`, que limpa a
mensagem ao ler.

---

## before_request

Em `app/routes/lancamentos.py` e `categorias.py`:

```python
@bp.before_request
@login_required
def exigir_login():
    """Protege todas as rotas do blueprint, sem repetir o decorator em cada uma."""
```

Roda antes de **toda** rota daquele blueprint. A função tem corpo vazio de
propósito: quem faz o trabalho é o `@login_required` empilhado acima dela.

A vantagem sobre decorar cada rota é que uma rota nova já nasce protegida —
esquecer o decorator deixaria de ser possível. Segurança por padrão, e não por
disciplina.

Note que `main.py` **não** usa isso: lá o `/health` precisa ficar público, e só
o `index` é decorado individualmente.

---

## Jinja

O motor de templates. Três marcações: `{{ valor }}` imprime, `{% %}` é lógica,
`{# #}` é comentário.

### Herança

`app/templates/base.html` tem o esqueleto com um buraco:

```jinja
<main>{% block content %}{% endblock %}</main>
```

E cada página preenche:

```jinja
{% extends "base.html" %}
{% block content %} ... {% endblock %}
```

Mudou o menu? Mexe só no `base.html`.

### Macros

`app/templates/_macros.html` define o `campo`, que desenha rótulo, entrada e
erros de um campo de formulário. É uma função de template:

```jinja
{% from "_macros.html" import campo %}
{{ campo(form.descricao) }}
```

### Filtros próprios

`app/filters.py` registra três filtros no ambiente Jinja:

```python
app.jinja_env.filters["moeda"] = moeda
```

Usados como `{{ valor|moeda }}`, `{{ data|data_br }}`, `{{ 3|mes_abrev }}`.
Formatação é apresentação — fica no template, não no model.

### Escape automático

Jinja escapa HTML por padrão. Um lançamento descrito como
`<script>alert(1)</script>` aparece como texto, não executa. É proteção contra
XSS de graça, perdida só se você usar `|safe`.

### Fragmentos e HTMX

`app/templates/lancamentos/_tabela.html` é incluído pela página inteira **e**
devolvido sozinho quando o HTMX pede:

```python
if request.headers.get("HX-Request"):
    return render_template("lancamentos/_tabela.html", **contexto)
return render_template("lancamentos/listar.html", **contexto)
```

Um template, dois usos. O navegador sem JavaScript recebe a página completa; o
HTMX recebe só o pedaço e troca na tela. É o que chamamos de *progressive
enhancement*: a funcionalidade não depende do JavaScript, só melhora com ele.

---

## Formulários e CSRF

`app/forms.py` declara os formulários com Flask-WTF:

```python
class LancamentoForm(FlaskForm):
    descricao = StringField("Descrição", validators=[DataRequired(...), Length(max=200)])
```

Na rota, o padrão é sempre o mesmo:

```python
form = LancamentoForm()
if form.validate_on_submit():     # True só em POST com dados válidos
    ...
    return redirect(...)
return render_template(...)       # GET, ou POST com erro
```

`validate_on_submit()` junta duas perguntas — "é POST?" e "passou na
validação?" — e é o que permite a rota tratar exibição e envio na mesma função.

### CSRF

`CSRFProtect` faz duas coisas: exige um token válido em todo POST e
disponibiliza `csrf_token()` nos templates.

Em formulários montados pelo WTForms, `{{ form.hidden_tag() }}` já inclui o
token. Nos formulários escritos à mão — como o de excluir, em `_tabela.html` —
é preciso colocar na mão:

```jinja
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}" />
```

Sem isso, o POST toma 400. O `scripts/smoke.py` verifica exatamente esse
comportamento, porque `TestingConfig` desliga o CSRF e o pytest não o exercita.

### Campo customizado

`ValorBRLField` estende `DecimalField` sobrescrevendo `process_formdata`, o
gancho que o WTForms chama para converter o texto do formulário no valor
Python. É onde `"1.234,56"` vira `Decimal("1234.56")`.

---

## Login

Flask-Login guarda o **id** do usuário na sessão (um cookie assinado) e o
recarrega a cada requisição.

Três peças em `app/extensions.py`:

```python
login_manager.login_view = "auth.login"    # para onde desviar quem não logou
login_manager.session_protection = "strong"

@login_manager.user_loader
def carregar_usuario(usuario_id: str):
    return db.session.get(Usuario, int(usuario_id))
```

O `user_loader` é obrigatório: é a ponte entre o id no cookie e o objeto. Note
que ele recebe **string** — o que vem do cookie é texto.

`Usuario` herda de `UserMixin`, que fornece `is_authenticated`, `is_anonymous` e
`get_id`. O projeto sobrescreve `is_active` para respeitar a coluna `ativo`:

```python
@property
def is_active(self) -> bool:
    return self.ativo
```

O Flask-Login consulta essa propriedade e recusa o login de conta desativada.

Nas rotas e templates, `current_user` é outro proxy: o usuário da requisição
atual, ou um objeto anônimo. Em `base.html`:

```jinja
{% if current_user.is_authenticated %}
```

`session_protection = "strong"` invalida a sessão se a impressão do navegador
mudar — defesa contra cookie roubado.

---

## Banco de dados

Flask-SQLAlchemy embrulha o SQLAlchemy e cuida da sessão por requisição.

### A sessão

`db.session` é uma sessão com escopo: cada requisição tem a sua, e ela é
descartada no fim. Por isso o padrão é sempre:

```python
db.session.add(objeto)
db.session.commit()
```

Sem `commit`, nada é gravado. E objetos já carregados são rastreados — em
`alterar_senha`, basta mexer no objeto e commitar; não há `update` explícito.

### Consultas

O projeto usa dois estilos, por razões diferentes:

```python
# clássico — conciso para filtros simples
Categoria.query.filter_by(usuario_id=usuario_id)

# 2.0 — necessário para db.one_or_404
db.one_or_404(db.select(Lancamento).filter_by(id=..., usuario_id=...))
```

`db.get_or_404` e `db.one_or_404` são conveniências do Flask-SQLAlchemy: em vez
de devolver `None`, abortam com 404. O projeto usa `one_or_404` com filtro de
dono — devolver 404 (e não 403) para registro alheio evita confirmar que aquele
id existe.

### Relacionamentos

```python
class Categoria(...):
    lancamentos = db.relationship("Lancamento", back_populates="categoria")

class Lancamento(...):
    categoria = db.relationship("Categoria", back_populates="lancamentos")
```

`back_populates` mantém os dois lados sincronizados em memória. O nome da classe
vai como **string** porque `Lancamento` ainda não existe quando `Categoria` é
declarada.

---

## Migrações

Flask-Migrate embrulha o Alembic. O ciclo é:

```bash
flask db migrate -m "descrição"   # compara models × banco e gera o script
flask db upgrade                  # aplica
flask db downgrade                # desfaz a última
```

O `migrate` **gera um rascunho**, e rascunho se revisa. Neste projeto duas
correções manuais foram necessárias:

- as foreign keys vinham sem nome, e `drop_constraint(None)` falha no SQLite no
  `downgrade`;
- colunas novas em tabelas com dados precisam ser `nullable=True`, ou a
  migração quebra em bancos já em uso.

O SQLite não sabe alterar colunas; o Alembic contorna com
`batch_alter_table`, que recria a tabela por baixo dos panos. É por isso que os
scripts têm aqueles blocos `with op.batch_alter_table(...)`.

Migrações ficam fora do `ruff` (veja `pyproject.toml`): são geradas, não
escritas à mão.

---

## Configuração

`app/config.py` usa classes, e `from_object` lê os atributos em MAIÚSCULAS:

```python
class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "...")

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
```

Herança dá os valores comuns de graça, e cada ambiente sobrescreve o que
precisa. `app.config` é um dicionário — extensões leem dele por convenção:
`SQLALCHEMY_DATABASE_URI`, `WTF_CSRF_ENABLED`, `SESSION_COOKIE_SAMESITE`,
`REMEMBER_COOKIE_DURATION`.

`SECRET_KEY` merece atenção: assina o cookie de sessão **e** os links de
redefinição de senha. Trocá-la desloga todo mundo e invalida os links
pendentes.

---

## Comandos de linha

`app/cli.py` registra comandos no `flask`:

```python
@app.cli.command("seed")
@click.option("--email", default=None, help="...")
def seed(email):
    ...
```

O Flask usa Click por baixo. Comandos assim rodam **dentro** de um application
context — daí `db.session` funcionar sem `with app.app_context()`.

Disponíveis: `init-db`, `criar-usuario`, `seed`, `limpar-tentativas`, mais os
`db *` do Flask-Migrate.

Criar conta pela linha de comando é decisão de segurança: não há cadastro
aberto pela web.

---

## Testes

### O cliente de teste

`app.test_client()` faz requisições **em memória**, sem rede nem servidor:

```python
resp = client.get("/lancamentos/")
resp = client.post("/login", data={...}, follow_redirects=True)
```

Ele mantém cookies entre chamadas — é por isso que a fixture `logado` faz login
uma vez e as requisições seguintes já vêm autenticadas.

### As fixtures

`tests/conftest.py` monta um app novo por teste, com SQLite em memória:

```python
@pytest.fixture
def app():
    app = create_app(TestingConfig)
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()
```

Nada toca o disco, e nenhum teste enxerga o dado do outro. É o que mantém 165
testes em ~6 segundos.

### O runner de CLI

`app.test_cli_runner()` invoca os comandos do `cli.py` sem subprocesso:

```python
resultado = runner.invoke(args=["seed", "--email", usuario.email])
assert "categoria(s) criada(s)" in resultado.output
```

### O que os testes não cobrem

`TestingConfig` desliga o CSRF e troca o hash de senha por um barato. Cada
ajuste desses é um pedaço do Flask que o pytest deixa de exercitar — e o motivo
de `scripts/smoke.py` existir, subindo o servidor de verdade.

Isso não é teoria: o link de redefinição era registrado em nível `INFO`, que o
Flask descarta fora do modo debug. O pytest passava porque `caplog.at_level`
forçava o nível. Só o smoke, olhando o log real, pegou.

---

## Para aprofundar

- [Documentação do Flask](https://flask.palletsprojects.com/)
- [Flask-SQLAlchemy](https://flask-sqlalchemy.readthedocs.io/)
- [Flask-Login](https://flask-login.readthedocs.io/)
- [Flask-WTF](https://flask-wtf.readthedocs.io/)
- [Jinja](https://jinja.palletsprojects.com/)
