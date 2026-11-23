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
