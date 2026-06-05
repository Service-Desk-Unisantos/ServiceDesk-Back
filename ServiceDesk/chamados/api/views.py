import json
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenBlacklistView, TokenRefreshView

from chamados.models import Chamado, Comentario, Notificacao
from chamados.views import enviar_notificacao_status_chamado

from .permissions import IsChamadoOwnerOrStaff, IsStaff
from .serializers import (
    CadastroSerializer,
    ChamadoSerializer,
    ComentarioSerializer,
    NotificacaoSerializer,
    UsuarioSerializer,
)

User = get_user_model()


def _tokens_para_usuario(user):
    refresh = RefreshToken.for_user(user)
    return {
        "refresh": str(refresh),
        "access":  str(refresh.access_token),
        "user":    UsuarioSerializer(user).data,
    }


# ── Auth ──────────────────────────────────────────────────────────────────────

class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get("username", "").strip()
        password = request.data.get("password", "")

        user = authenticate(request, username=username, password=password)
        if user is None:
            return Response(
                {"detail": "Usuário ou senha incorretos."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        return Response(_tokens_para_usuario(user))


class CadastroView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = CadastroSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(_tokens_para_usuario(user), status=status.HTTP_201_CREATED)


# TokenRefreshView e TokenBlacklistView vêm direto do simplejwt
__all__ = ["TokenRefreshView", "TokenBlacklistView"]


@login_required
def google_auth_success(request):
    dados = _tokens_para_usuario(request.user)
    fragmento = urlencode(
        {
            "access": dados["access"],
            "refresh": dados["refresh"],
            "user": json.dumps(dados["user"], ensure_ascii=False),
        }
    )
    return redirect(f"{settings.FRONTEND_GOOGLE_CALLBACK_URL}#{fragmento}")


# ── Chamados ──────────────────────────────────────────────────────────────────

class ChamadoViewSet(viewsets.ModelViewSet):
    serializer_class   = ChamadoSerializer
    permission_classes = [IsAuthenticated]
    http_method_names  = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return Chamado.objects.select_related("usuario").all()
        return Chamado.objects.select_related("usuario").filter(usuario=user)

    def get_permissions(self):
        if self.action in ("partial_update",):
            return [IsStaff()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        serializer.save(usuario=self.request.user)

    def partial_update(self, request, *args, **kwargs):
        chamado = self.get_object()
        status_anterior = chamado.status

        serializer = self.get_serializer(chamado, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        chamado_atualizado = serializer.save()

        if chamado_atualizado.status != status_anterior:
            enviar_notificacao_status_chamado(chamado_atualizado)

        return Response(serializer.data)


# ── Comentários ───────────────────────────────────────────────────────────────

class ComentarioViewSet(viewsets.ModelViewSet):
    serializer_class   = ComentarioSerializer
    permission_classes = [IsAuthenticated]
    http_method_names  = ["get", "post", "head", "options"]

    def get_queryset(self):
        chamado_pk = self.kwargs.get("chamado_pk")
        return Comentario.objects.filter(chamado_id=chamado_pk).select_related("usuario")

    def get_permissions(self):
        if self.action == "create":
            return [IsAuthenticated(), IsChamadoOwnerOrStaff()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        chamado_pk = self.kwargs.get("chamado_pk")
        chamado    = Chamado.objects.get(pk=chamado_pk)
        self.check_object_permissions(self.request, chamado)
        serializer.save(chamado=chamado, usuario=self.request.user)


# ── Notificações ──────────────────────────────────────────────────────────────

class NotificacaoViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class   = NotificacaoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Notificacao.objects.filter(
            usuario=self.request.user, lida=False
        ).select_related("chamado")

    @action(detail=False, methods=["post"], url_path="marcar-lidas")
    def marcar_lidas(self, request):
        Notificacao.objects.filter(usuario=request.user, lida=False).update(lida=True)
        return Response({"detail": "Notificações marcadas como lidas."})
