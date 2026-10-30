from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils.text import slugify
from rest_framework import serializers

from chamados.models import Categoria, Chamado, Comentario, HistoricoChamado, Notificacao

User = get_user_model()


class UsuarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "is_staff", "is_superuser"]
        read_only_fields = fields


class CadastroSerializer(serializers.Serializer):
    username   = serializers.CharField(max_length=150)
    email      = serializers.EmailField()
    first_name = serializers.CharField(max_length=150, required=False, default="")
    last_name  = serializers.CharField(max_length=150, required=False, default="")
    password1  = serializers.CharField(write_only=True)
    password2  = serializers.CharField(write_only=True)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Este nome de usuário já está em uso.")
        return value

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Este e-mail já está cadastrado.")
        return value

    def validate(self, data):
        if data["password1"] != data["password2"]:
            raise serializers.ValidationError({"password2": "As senhas não coincidem."})
        validate_password(data["password1"])
        return data

    def create(self, validated_data):
        return User.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
            password=validated_data["password1"],
        )


class CategoriaSerializer(serializers.ModelSerializer):
    # default explícito: em requisições de formulário o DRF trataria a ausência como False.
    ativa          = serializers.BooleanField(default=True)
    total_chamados = serializers.IntegerField(read_only=True)

    class Meta:
        model  = Categoria
        fields = ["id", "nome", "slug", "ativa", "total_chamados"]
        read_only_fields = ["id", "slug", "total_chamados"]

    def validate_nome(self, value):
        nome = value.strip()
        slug = slugify(nome)
        if not slug:
            raise serializers.ValidationError("Informe um nome com letras ou números.")

        outras = Categoria.objects.exclude(pk=self.instance.pk) if self.instance else Categoria.objects.all()
        if outras.filter(nome__iexact=nome).exists():
            raise serializers.ValidationError("Já existe uma categoria com este nome.")
        # O slug só é gerado na criação; ao renomear ele permanece o mesmo.
        if self.instance is None and outras.filter(slug=slug).exists():
            raise serializers.ValidationError("Já existe uma categoria com nome equivalente.")
        return nome


class ChamadoSerializer(serializers.ModelSerializer):
    usuario          = serializers.PrimaryKeyRelatedField(read_only=True)
    usuario_username = serializers.SerializerMethodField()
    # Recebe e devolve o slug ("hardware", "rede"...); só aceita categorias ativas.
    categoria        = serializers.SlugRelatedField(
        slug_field="slug", queryset=Categoria.objects.filter(ativa=True)
    )
    categoria_nome   = serializers.CharField(source="categoria.nome", read_only=True)

    class Meta:
        model  = Chamado
        fields = [
            "id", "titulo", "descricao", "categoria", "categoria_nome", "prioridade",
            "status", "usuario", "usuario_username", "data_criacao",
        ]
        read_only_fields = ["id", "categoria_nome", "usuario", "usuario_username", "data_criacao"]

    def get_usuario_username(self, obj):
        return obj.usuario.username


class ComentarioSerializer(serializers.ModelSerializer):
    usuario          = serializers.PrimaryKeyRelatedField(read_only=True)
    usuario_username = serializers.SerializerMethodField()

    class Meta:
        model  = Comentario
        fields = ["id", "chamado", "usuario", "usuario_username", "texto", "data"]
        read_only_fields = ["id", "chamado", "usuario", "usuario_username", "data"]

    def get_usuario_username(self, obj):
        return obj.usuario.username


class NotificacaoSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Notificacao
        fields = ["id", "mensagem", "tipo", "chamado", "lida", "criada_em"]
        read_only_fields = fields


class HistoricoChamadoSerializer(serializers.ModelSerializer):
    autor_username = serializers.SerializerMethodField()
    acao_display   = serializers.CharField(source="get_acao_display", read_only=True)

    class Meta:
        model  = HistoricoChamado
        fields = [
            "id", "autor", "autor_username", "acao", "acao_display",
            "atributo", "valor_anterior", "valor_novo", "data",
        ]
        read_only_fields = fields

    def get_autor_username(self, obj):
        return obj.autor.username if obj.autor else ""
