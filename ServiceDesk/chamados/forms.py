from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User

from .models import Categoria, Chamado


class ChamadoForm(forms.ModelForm):
    class Meta:
        model = Chamado
        # Campos necessarios para o registro do chamado, incluindo categoria (RF03).
        fields = ["titulo", "descricao", "categoria", "prioridade"]
        widgets = {
            "titulo": forms.TextInput(
                attrs={"placeholder": "Ex.: Erro ao acessar o sistema interno"}
            ),
            "descricao": forms.Textarea(
                attrs={"placeholder": "Descreva o problema com o maximo de detalhes"}
            ),
            "categoria": forms.Select(),
            "prioridade": forms.Select(),
        }

    def __init__(self, *args, **kwargs):
        # Somente categorias ativas, cadastradas pelos administradores, aparecem na abertura.
        super().__init__(*args, **kwargs)
        self.fields["categoria"].queryset = Categoria.objects.filter(ativa=True)


class CadastroUsuarioForm(UserCreationForm):
    # Campo extra para o cadastro do usuario (RF01).
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "email", "password1", "password2")
        labels = {
            "username": "Usuario",
            "first_name": "Nome",
            "last_name": "Sobrenome",
            "email": "E-mail",
            "password1": "Senha",
            "password2": "Confirmacao da senha",
        }

    def __init__(self, *args, **kwargs):
        # Aplica classe padrao para garantir alinhamento correto dos campos no frontend.
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            classes_atuais = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{classes_atuais} form-control".strip()


class LoginUsuarioForm(AuthenticationForm):
    username = forms.CharField(
        label="Usuario ou e-mail",
        widget=forms.TextInput(
            attrs={
                "autofocus": True,
                "placeholder": "Digite seu usuario ou e-mail",
            }
        ),
    )
    # Campo de senha explicito para manter placeholder e compatibilidade com botao de olho.
    password = forms.CharField(
        label="Senha",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "current-password",
                "placeholder": "Digite sua senha",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        # Aplica classe padrao para o layout dos campos de login e do toggle de senha.
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            classes_atuais = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{classes_atuais} form-control".strip()


class AtualizacaoChamadoAdminForm(forms.Form):
    # Campos que a equipe de infra pode atualizar durante o atendimento.
    status = forms.ChoiceField(choices=Chamado.STATUS_CHOICES, label="Status")
    prioridade = forms.ChoiceField(
        choices=Chamado.PRIORIDADE_CHOICES,
        label="Prioridade",
    )
    # Campo opcional para registrar resposta tecnica no historico do chamado.
    resposta = forms.CharField(
        label="Resposta da equipe",
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Descreva a analise, orientacao ou solucao aplicada",
            }
        ),
    )

    def __init__(self, *args, chamado=None, **kwargs):
        # Inicializa o formulario com os valores atuais do chamado selecionado.
        super().__init__(*args, **kwargs)
        if chamado is not None:
            self.fields["status"].initial = chamado.status
            self.fields["prioridade"].initial = chamado.prioridade

        # Aplica classes visuais para manter consistencia com o template Bootstrap.
        self.fields["status"].widget.attrs["class"] = "form-select"
        self.fields["prioridade"].widget.attrs["class"] = "form-select"
        self.fields["resposta"].widget.attrs["class"] = "form-control"


class MensagemChamadoForm(forms.Form):
    # Campo simples para conversa entre cliente e equipe no chamado.
    mensagem = forms.CharField(
        label="Mensagem",
        required=True,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "class": "form-control",
                "placeholder": "Escreva sua mensagem para a equipe",
            }
        ),
    )
