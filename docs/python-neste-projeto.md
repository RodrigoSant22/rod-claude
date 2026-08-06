# Python neste projeto

As construções da linguagem e da biblioteca padrão usadas no código, com o
motivo de cada escolha. Companheiro de [Flask neste projeto](flask-neste-projeto.md),
que cobre o framework.

- [Decimal: dinheiro nunca em float](#decimal-dinheiro-nunca-em-float)
- [StrEnum](#strenum)
- [dataclass](#dataclass)
- [property](#property)
- [Mixins e ordem de herança](#mixins-e-ordem-de-herança)
- [Anotações de tipo](#anotações-de-tipo)
- [Geradores e o yield das fixtures](#geradores-e-o-yield-das-fixtures)
- [Gerenciadores de contexto](#gerenciadores-de-contexto)
- [Compreensões](#compreensões)
- [Desempacotamento e **kwargs](#desempacotamento-e-kwargs)
- [Módulos da biblioteca padrão](#módulos-da-biblioteca-padrão)
- [Verdade e falsidade](#verdade-e-falsidade)
- [Exceções](#exceções)

---

## Decimal: dinheiro nunca em float

A decisão mais importante do projeto, e a menos negociável:

```python
>>> 0.1 + 0.2
0.30000000000000004
```

`float` é binário. Números como 0,1 não têm representação exata em base 2, do
mesmo jeito que 1/3 não tem em base 10. Some mil lançamentos e o saldo não
fecha.

`Decimal` guarda os dígitos decimais como você os escreveu:

```python
>>> from decimal import Decimal
>>> Decimal("0.1") + Decimal("0.2")
Decimal('0.3')
```

**Sempre construa a partir de string.** `Decimal(0.1)` recebe o float já
impreciso e herda o erro:

```python
>>> Decimal(0.1)
Decimal('0.1000000000000000055511151231257827021181583404541015625')
```

No projeto:

- `app/models.py` — `db.Column(db.Numeric(12, 2))` faz o SQLAlchemy devolver
  `Decimal`, não `float`
- `app/services.py` — `Decimal(str(total))` converte o retorno agregado do banco
  passando por string
- `app/forms.py` — `Decimal(bruto).quantize(Decimal("0.01"))` normaliza para
  dois dígitos

`quantize` arredonda para um número fixo de casas. Sem ele, `Decimal("10")/3`
teria 28 dígitos.

`tests/test_models.py::test_soma_decimal_nao_acumula_erro` trava esse
comportamento.

---

## StrEnum

```python
class TipoLancamento(StrEnum):
    RECEITA = "receita"
    DESPESA = "despesa"

    @property
    def rotulo(self) -> str:
        return "Receita" if self is TipoLancamento.RECEITA else "Despesa"
```

`StrEnum` (Python 3.11+) é enum cujos membros **são** strings. Dá para comparar,
concatenar e serializar como texto, sem `.value`:

```python
>>> TipoLancamento.RECEITA == "receita"
True
>>> f"tipo-{TipoLancamento.DESPESA}"
'tipo-despesa'
```

Por que enum e não string solta: `TipoLancamento.RECEITA` é verificável — um
erro de digitação vira `AttributeError` na hora, enquanto `"receta"` só falha
silenciosamente em produção.

Repare que enums aceitam métodos e propriedades. `rotulo` mantém o texto de
exibição junto do dado, em vez de espalhar `if tipo == "receita": "Receita"`
pelos templates.

No projeto o enum vira coluna:

```python
tipo = db.Column(db.Enum(TipoLancamento, native_enum=False), nullable=False)
```

`native_enum=False` grava como texto com uma constraint, em vez de usar o tipo
`ENUM` do banco — mais portátil entre SQLite e Postgres.

### Comparação: `is` ou `==`?

O código usa `is` para enums:

```python
if self.tipo is TipoLancamento.DESPESA:
```

Membros de enum são singletons, então `is` funciona e comunica melhor a
intenção: "é este membro", não "tem este valor".

---

## dataclass

```python
@dataclass(frozen=True)
class Resumo:
    receitas: Decimal
    despesas: Decimal

    @property
    def saldo(self) -> Decimal:
        return self.receitas - self.despesas
```

O decorador gera `__init__`, `__repr__` e `__eq__` a partir das anotações.
Escreve-se três linhas em vez de quinze.

`frozen=True` torna as instâncias imutáveis: tentar `resumo.receitas = 0`
levanta erro. Para um objeto de retorno — um valor calculado que ninguém
deveria alterar depois — imutabilidade evita uma classe inteira de bug.

`saldo` é derivado, não armazenado. Não há como o saldo divergir das parcelas.

`TotalCategoria`, em `app/services.py`, e `Bloqueio`, em `app/seguranca.py`,
seguem o mesmo padrão. Este último ainda define:

```python
def __bool__(self) -> bool:
    return self.bloqueado
```

O que permite escrever `if bloqueio:` em vez de `if bloqueio.bloqueado:`.

---

## property

Transforma método em atributo de leitura:

```python
@property
def valor_com_sinal(self) -> Decimal:
    if self.tipo is TipoLancamento.DESPESA:
        return -self.valor
    return self.valor
```

Usa-se `lancamento.valor_com_sinal`, sem parênteses.

O ganho aqui não é sintático, é de consistência: `tipo` é uma property que
delega para `self.categoria.tipo`. Como não existe coluna `tipo` em
`Lancamento`, é **impossível** um lançamento contradizer a categoria dele. A
regra vira estrutura, e não disciplina.

`Categoria.em_uso` faz uma consulta ao banco por trás da property. É um caso
limite: property deve ser barata, e uma query não é. Vale porque a chamada é
pontual, na tela de exclusão — se fosse dentro de um laço, seria erro de
projeto (o clássico N+1).

---

## Mixins e ordem de herança

```python
class TimestampMixin:
    created_at = db.Column(...)
    updated_at = db.Column(...)


class Usuario(TimestampMixin, UserMixin, db.Model):
    ...
```

Um mixin não é usado sozinho — só empresta atributos a quem herdar dele. Três
modelos herdam `TimestampMixin` sem repetir as colunas.

A ordem importa. Python resolve atributos da esquerda para a direita (MRO):
`TimestampMixin` antes de `UserMixin` antes de `db.Model`. Mixins vêm primeiro
justamente para poderem sobrescrever o comportamento da classe base.

`UserMixin` vem do Flask-Login e fornece `is_authenticated`, `is_anonymous` e
`get_id`. `Usuario` sobrescreve `is_active` com uma property própria — e é a
posição na MRO que garante que a versão da subclasse ganhe.

---

## Anotações de tipo

O projeto anota assinaturas:

```python
def calcular_resumo(
    usuario_id: int, inicio: date | None = None, fim: date | None = None
) -> Resumo:
```

Python **não** verifica isso em tempo de execução — anotação é documentação
legível por ferramenta. O valor está no editor: autocompletar, navegação e
detecção de erro antes de rodar.

`date | None` é a sintaxe moderna (3.10+) para o antigo `Optional[date]`. Lê-se
"data ou nada".

Outras formas usadas:

```python
list[Lancamento]                       # lista de lançamentos
dict[str, str]                         # dicionário de string para string
dict[tuple[str, str], Decimal]         # chave composta
str | type[Config] | None              # três possibilidades
```

`type[Config]` é a *classe* `Config`, não uma instância — `create_app` aceita
tanto o nome do preset quanto a classe.

Uma anotação também documenta intenção onde o valor não deixa claro:

```python
janela: timedelta = current_app.config[_POLITICAS[acao][2]]
```

O `config` devolve `Any`; a anotação diz ao leitor o que esperar.

---

## Geradores e o yield das fixtures

```python
@pytest.fixture
def app():
    app = create_app(TestingConfig)
    with app.app_context():
        _db.create_all()
        yield app          # o teste roda aqui
        _db.session.remove()
        _db.drop_all()
```

A função tem `yield`, então é um gerador: executa até o `yield`, entrega o
valor, e **pausa**. O pytest roda o teste, e depois retoma a função de onde
parou para executar a limpeza.

É o mesmo mecanismo de `contextlib.contextmanager`: preparação antes,
finalização depois, sem precisar de `try/finally` no teste.

Consequência prática: cada teste ganha um banco novo e o descarta. Nenhum teste
enxerga o resíduo do anterior.

---

## Gerenciadores de contexto

O `with` garante limpeza mesmo com exceção no meio.

```python
with smtplib.SMTP(servidor, porta, timeout=15) as smtp:
    smtp.send_message(mensagem)
```

A conexão fecha ao sair do bloco, dando erro ou não.

```python
with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    return s.getsockname()[1]
```

Truque em `scripts/smoke.py`: porta 0 faz o sistema escolher uma livre. Lê-se
qual foi, fecha o socket e usa o número — evita adivinhar porta e colidir.

O `scripts/smoke.py` também usa `try/finally` para o encerramento do servidor.
Onde não há gerenciador de contexto pronto, o `finally` faz o papel: o servidor
morre e a pasta temporária some mesmo se uma verificação estourar.

---

## Compreensões

```python
# lista
[TotalCategoria(...) for nome, total in linhas]

# dicionário
{tipo: Decimal(str(total)) for tipo, total in query}

# conjunto
{aba.cell(row=n, column=4).value for n in range(2, aba.max_row + 1)}

# gerador (parênteses, avaliado sob demanda)
sum((item.valor for item in lancamentos if item.tipo is TipoLancamento.RECEITA), Decimal("0.00"))
```

O segundo argumento de `sum` é o valor inicial. Sem ele, `sum` começa do `int`
`0` e misturar `int` com `Decimal` daria erro — por isso `Decimal("0.00")`
explícito.

Uma compreensão aninhada em `app/seguranca.py` monta filtros dinamicamente:

```python
*[getattr(TentativaAcesso, campo) == valor for campo, valor in filtros.items()]
```

`getattr` acessa o atributo pelo nome em string, e o `*` desempacota a lista
como argumentos posicionais de `filter()`. É o que permite a mesma função
filtrar por conta ou por IP sem duplicar código.

---

## Desempacotamento e **kwargs

```python
contexto = {
    "lancamentos": ...,
    "filtros": filtros,
    **_links_exportacao(filtros),      # funde outro dicionário aqui
}
return render_template("lancamentos/listar.html", **contexto)
```

`**` desempacota o dicionário em argumentos nomeados. `render_template(**ctx)`
equivale a passar cada chave como parâmetro.

Em `app/routes/lancamentos.py`:

```python
services.buscar_lancamentos(current_user.id, **filtros)
```

O dicionário `filtros` tem exatamente as chaves que a função espera — `inicio`,
`fim`, `tipo`, `categoria_id`, `texto`. Conciso, mas com um custo: renomear um
parâmetro da função quebra a chamada em tempo de execução, não de escrita.

Ordem em `{**padrao, **extras}`: o segundo vence. É o idioma para "valores
padrão que o chamador pode sobrescrever", usado no helper de
`tests/test_mailer.py`.

---

## Módulos da biblioteca padrão

Boa parte do projeto não precisou de dependência externa:

| Módulo | Onde | Para quê |
| --- | --- | --- |
| `decimal` | models, services, forms | Aritmética exata |
| `datetime` | models, services | Datas, horas com fuso, `timedelta` |
| `enum` | models | `StrEnum` |
| `dataclasses` | services, seguranca | Objetos de valor |
| `csv` | exportacao | Escrita de CSV |
| `io` | exportacao | `StringIO`, `BytesIO` como arquivo em memória |
| `hashlib` | tokens | SHA-256 da impressão do hash |
| `smtplib` + `email.message` | mailer | Envio de e-mail |
| `urllib.parse` | routes/auth | Análise da URL do `?next=` |
| `pathlib` | config, `__init__` | Caminhos |
| `subprocess`, `socket`, `tempfile` | smoke | Orquestração do teste |

Sobre datas: o projeto usa `datetime.now(UTC)`, nunca `utcnow()`. O segundo
devolve um datetime **sem fuso** — um objeto que parece UTC mas não se
identifica como tal, e que compara errado com datetimes que têm fuso. Está
depreciado no Python 3.12.

`app/seguranca.py` lida com o caso em que o banco devolve sem fuso:

```python
if criado.tzinfo is None:
    criado = criado.replace(tzinfo=utcnow().tzinfo)
```

Sobre `io`: `StringIO` e `BytesIO` são arquivos em memória. O módulo `csv` e o
`openpyxl` escrevem neles como escreveriam em disco, e o resultado vai direto
para a resposta HTTP — sem arquivo temporário.

---

## Verdade e falsidade

Isso causou um bug real neste projeto.

Em Python, `0`, `0.0`, `Decimal("0.00")`, `""`, `[]`, `{}` e `None` são falsos.
O validador `DataRequired` do WTForms testa exatamente isso — e recusava um
lançamento de valor zero com a mensagem **"Informe o valor"**, como se o campo
estivesse vazio.

```python
InputRequired("Informe o valor."),                    # olha o texto enviado
NumberRange(min=Decimal("0.01"), message="..."),      # aí sim valida a faixa
```

`InputRequired` verifica se algo foi digitado, não se o valor é verdadeiro. A
distinção existe justamente para campos numéricos onde zero é uma entrada
legítima.

O mesmo cuidado aparece em `app/models.py`:

```python
metodo = current_app.config.get(...) if current_app else None
```

`if current_app` não pergunta se o objeto existe — pergunta se o proxy tem um
contexto ativo por trás.

E em `app/filters.py`:

```python
if valor is None:
    return "R$ 0,00"
```

`is None` explícito, porque `if not valor` trataria `Decimal("0.00")` como
ausente.

---

## Exceções

### Encadeamento

```python
except (InvalidOperation, ValueError) as err:
    raise ValueError("Valor inválido...") from err
```

`from err` preserva a exceção original no traceback. Sem ele, a causa raiz
some e o rastro vira `During handling of the above exception, another
exception occurred` — confuso. O `ruff` cobra isso pela regra `B904`.

### Captura ampla, justificada

```python
try:
    db.session.execute(db.text("SELECT 1"))
except Exception:
    return {"status": "degraded", "database": "unreachable"}, 503
```

Capturar `Exception` normalmente é ruim: esconde bug. Aqui é o certo — uma
checagem de saúde precisa responder "degradado" para *qualquer* falha, não
apenas as previstas.

Em `app/mailer.py`, a captura é mais específica e tem outra razão:

```python
except (smtplib.SMTPException, OSError):
    current_app.logger.exception("Falha ao enviar e-mail para %s", destino)
    return False
```

Deixar a exceção subir mudaria a resposta HTTP conforme o e-mail existisse ou
não — vazando exatamente a informação que o fluxo tenta esconder.

`logger.exception` registra a mensagem **com** o traceback, e só funciona
dentro de um `except`.

### Log com `%s`, não f-string

```python
current_app.logger.warning("Para: %s\nAssunto: %s", destino, assunto)
```

Os argumentos só são interpolados se aquele nível de log estiver ativo. Com
f-string, a formatação acontece sempre, mesmo quando a mensagem é descartada.

---

## Detalhes menores que aparecem no código

**`_` como prefixo** — `_linhas`, `_meu_lancamento`, `_POLITICAS` são
privados por convenção. Python não impede o acesso; o prefixo comunica "não é
API deste módulo".

**`__repr__`** — definido nos models para o depurador e o log mostrarem
`<Categoria Moradia (despesa)>` em vez de `<Categoria object at 0x7f...>`.

**`@staticmethod`** — `Usuario.normalizar_email` não usa `self`, então é
chamável na classe: `Usuario.normalizar_email(texto)`.

**Barra invertida em strings** — `f"%{texto}%"` no `ilike` é o curinga do SQL,
não do Python.

**`sorted` com `key`** — `key=lambda item: item[1]` ordena pelo segundo elemento
da tupla; `reverse=True` inverte.

**`enumerate(..., start=1)`** — colunas de planilha começam em 1, não em 0.

**`int | float | Decimal` no `isinstance`** — a sintaxe de união também funciona
em `isinstance` a partir do 3.10.

---

## Para aprofundar

- [decimal — Aritmética decimal](https://docs.python.org/pt-br/3/library/decimal.html)
- [enum](https://docs.python.org/pt-br/3/library/enum.html)
- [dataclasses](https://docs.python.org/pt-br/3/library/dataclasses.html)
- [typing](https://docs.python.org/pt-br/3/library/typing.html)
