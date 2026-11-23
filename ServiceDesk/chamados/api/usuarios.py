from django.contrib.auth import get_user_model
from rest_framework.response import Response
from rest_framework.views import APIView

from .permissions import IsStaff

User = get_user_model()


class UsuarioListView(APIView):
    """GET /api/v1/usuarios/ — lista usuarios ativos (somente staff).

    Usado pelo admin para abrir um chamado em nome de outra pessoa.
    """

    permission_classes = [IsStaff]

    def get(self, request):
        usuarios = User.objects.filter(is_active=True).order_by("username")
        return Response([
            {
                "id": u.id,
                "username": u.username,
                "nome": f"{u.first_name} {u.last_name}".strip(),
                "email": u.email,
            }
            for u in usuarios
        ])


class UsuarioCadastradoListView(APIView):
    """GET /api/v1/usuarios/cadastrados/ — todos os usuarios da plataforma (somente staff).

    Alimenta a tela de gestao de usuarios. Diferente de UsuarioListView, inclui
    usuarios inativos e dados de perfil e ultimo acesso.
    """

    permission_classes = [IsStaff]

    def get(self, request):
        usuarios = User.objects.order_by("username")
        return Response([
            {
                "id": u.id,
                "username": u.username,
                "nome": f"{u.first_name} {u.last_name}".strip(),
                "email": u.email,
                "perfil": "administrador" if (u.is_staff or u.is_superuser) else "cliente",
                "is_active": u.is_active,
                "data_cadastro": u.date_joined,
                "ultimo_acesso": u.last_login,
            }
            for u in usuarios
        ])
