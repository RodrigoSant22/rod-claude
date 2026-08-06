"""Formulários da aplicação, com Flask-WTF.

Cada classe declara campos e validadores; a rota chama `validate_on_submit()`,
que responde True apenas quando a requisição é POST **e** os dados passam.
O token CSRF entra sozinho via `{{ form.hidden_tag() }}` no template.
"""

from decimal import Decimal, InvalidOperation

from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    DateField,
    DecimalField,
    PasswordField,
    SelectField,
    StringField,
    TextAreaField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    InputRequired,
    Length,
    NumberRange,
    Optional,
)

from app.models import TipoLancamento

# Comprimento mínimo de senha, cobrado no formulário e no `flask criar-usuario`.
SENHA_MINIMA = 8


class LoginForm(FlaskForm):
    """Entrada no sistema. O campo `lembrar` liga o cookie de longa duração."""

    email = StringField(
        "E-mail", validators=[DataRequired("Informe o e-mail."), Email("E-mail inválido.")]
    )
    senha = PasswordField("Senha", validators=[DataRequired("Informe a senha.")])
    lembrar = BooleanField("Manter conectado")


class EsqueciSenhaForm(FlaskForm):
    """Pedido de link de redefinição. Só o e-mail; a resposta nunca revela
    se ele existe."""

    email = StringField(
        "E-mail", validators=[DataRequired("Informe o e-mail."), Email("E-mail inválido.")]
    )


class RedefinirSenhaForm(FlaskForm):
    """Escolha da nova senha a partir do link recebido.

    Não pede a senha atual: quem chega aqui provou ter acesso ao e-mail, que
    é justamente o caso de quem esqueceu a senha.
    """

    nova_senha = PasswordField(
        "Nova senha",
        validators=[
            DataRequired("Informe a nova senha."),
            Length(min=SENHA_MINIMA, message=f"Use ao menos {SENHA_MINIMA} caracteres."),
        ],
    )
    confirmacao = PasswordField(
        "Confirme a nova senha",
        validators=[
            DataRequired("Repita a nova senha."),
            EqualTo("nova_senha", message="As senhas não conferem."),
        ],
    )


class AlterarSenhaForm(FlaskForm):
    """Troca de senha por quem já está autenticado.

    Exige a senha atual: sem isso, uma sessão esquecida aberta permitiria a
    qualquer um assumir a conta de vez.
    """

    senha_atual = PasswordField("Senha atual", validators=[DataRequired("Informe a senha atual.")])
    nova_senha = PasswordField(
        "Nova senha",
        validators=[
            DataRequired("Informe a nova senha."),
            Length(min=SENHA_MINIMA, message=f"Use ao menos {SENHA_MINIMA} caracteres."),
        ],
    )
    confirmacao = PasswordField(
        "Confirme a nova senha",
        validators=[
            DataRequired("Repita a nova senha."),
            EqualTo("nova_senha", message="As senhas não conferem."),
        ],
    )


class ValorBRLField(DecimalField):
    """DecimalField que aceita valores digitados no formato brasileiro.

    "1.234,56" e "1234.56" resultam ambos em Decimal("1234.56").
    """

    def process_formdata(self, valuelist):
        """Converte o texto vindo do formulário em Decimal.

        `process_formdata` é o gancho que o WTForms chama com a lista de
        valores brutos do campo. Levantar ValueError aqui vira mensagem de
        erro no formulário.
        """
        if not valuelist or not valuelist[0].strip():
            self.data = None
            return

        bruto = valuelist[0].strip().replace("R$", "").strip()
        # Vírgula presente indica notação brasileira: ponto é separador de milhar.
        if "," in bruto:
            bruto = bruto.replace(".", "").replace(",", ".")

        try:
            self.data = Decimal(bruto).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError) as err:
            self.data = None
            raise ValueError(
                self.gettext("Valor inválido. Use, por exemplo, 1.234,56")
            ) from err


class CategoriaForm(FlaskForm):
    """Cadastro de categoria. O tipo define se os lançamentos dela somam ou
    subtraem do saldo."""

    nome = StringField("Nome", validators=[DataRequired("Informe o nome."), Length(max=60)])
    tipo = SelectField(
        "Tipo",
        choices=[(t.value, t.rotulo) for t in TipoLancamento],
        validators=[DataRequired("Escolha o tipo.")],
    )
    ativa = BooleanField("Ativa", default=True)


class LancamentoForm(FlaskForm):
    """Cadastro e edição de lançamento.

    As opções de categoria não são declaradas aqui: dependem do usuário logado
    e são carregadas pela rota, com `carregar_categorias`.
    """

    descricao = StringField(
        "Descrição", validators=[DataRequired("Informe a descrição."), Length(max=200)]
    )
    valor = ValorBRLField(
        "Valor",
        places=2,
        validators=[
            # InputRequired, e não DataRequired: Decimal("0.00") é falsy, e o
            # DataRequired diria "informe o valor" para quem digitou zero.
            InputRequired("Informe o valor."),
            NumberRange(min=Decimal("0.01"), message="O valor deve ser maior que zero."),
        ],
    )
    data = DateField("Data", validators=[DataRequired("Informe a data.")])
    categoria_id = SelectField("Categoria", coerce=int, validators=[DataRequired()])
    observacao = TextAreaField("Observação", validators=[Optional(), Length(max=1000)])

    def carregar_categorias(self, categorias) -> None:
        """Preenche as opções do `<select>` com as categorias recebidas.

        Chamado pela rota com as categorias ativas do usuário logado. Como o
        `SelectField` valida contra esta lista, uma categoria de outra conta
        enviada à força é recusada.
        """
        self.categoria_id.choices = [
            (c.id, f"{c.tipo.rotulo} · {c.nome}") for c in categorias
        ]


class FiltroLancamentosForm(FlaskForm):
    """Filtros da listagem.

    Enviado por GET e sem efeito colateral, então dispensa token CSRF — que
    além de desnecessário sujaria a URL compartilhável.
    """

    class Meta:
        """Configuração do WTForms para este formulário."""

        csrf = False  # Filtro é GET e não altera estado.

    inicio = DateField("De", validators=[Optional()])
    fim = DateField("Até", validators=[Optional()])
    tipo = SelectField(
        "Tipo",
        choices=[("", "Todos")] + [(t.value, t.rotulo) for t in TipoLancamento],
        validators=[Optional()],
    )
    categoria_id = SelectField("Categoria", validators=[Optional()])
    texto = StringField("Busca", validators=[Optional(), Length(max=100)])
