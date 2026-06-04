from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from chamados.models import Chamado, Comentario, Notificacao

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


class ChamadoSerializer(serializers.ModelSerializer):
    usuario          = serializers.PrimaryKeyRelatedField(read_only=True)
    usuario_username = serializers.SerializerMethodField()

    class Meta:
        model  = Chamado
        fields = [
            "id", "titulo", "descricao", "categoria", "prioridade",
            "status", "usuario", "usuario_username", "data_criacao",
        ]
        read_only_fields = ["id", "usuario", "usuario_username", "data_criacao"]

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
