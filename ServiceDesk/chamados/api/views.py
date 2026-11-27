import json
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.db.models import Count

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenBlacklistView, TokenRefreshView

from chamados.models import (
    Categoria,
    Chamado,
    Comentario,
    HistoricoChamado,
    Notificacao,
    _resumo,
    registrar_edicoes,
)
from chamados.notificacoes import enviar_notificacao_status_chamado

from .permissions import IsChamadoOwnerOrStaff, IsStaff
from .serializers import (
    CadastroSerializer,
    CategoriaSerializer,
    ChamadoSerializer,
    ComentarioSerializer,
    HistoricoChamadoSerializer,
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


def google_login_guard(request):
    # Inicia o login Google; sem credenciais configuradas, volta para o login do frontend.
    if not settings.GOOGLE_OAUTH_ENABLED:
        return redirect(f"{settings.FRONTEND_LOGIN_URL}?google_error=1")

    from allauth.socialaccount.providers.google.views import oauth2_login

    return oauth2_login(request)


@never_cache
@login_required
def google_auth_success(request):
    # So uma sessao aberta pelo Google pode virar JWT (sessao do admin, por exemplo, nao).
    metodos = request.session.get("account_authentication_methods", [])
    if not any(
        m.get("method") == "socialaccount" and m.get("provider") == "google"
        for m in metodos
    ):
        return redirect(f"{settings.FRONTEND_LOGIN_URL}?google_error=1")

    dados = _tokens_para_usuario(request.user)
    fragmento = urlencode(
        {
            "access": dados["access"],
            "refresh": dados["refresh"],
            "user": json.dumps(dados["user"], ensure_ascii=False),
        }
    )
    # A sessao serve apenas para esta troca: encerrada, a URL nao gera novos tokens.
    logout(request)
    return redirect(f"{settings.FRONTEND_GOOGLE_CALLBACK_URL}#{fragmento}")


# ── Categorias ────────────────────────────────────────────────────────────────

class CategoriaViewSet(viewsets.ModelViewSet):
    serializer_class   = CategoriaSerializer
    pagination_class   = None
    http_method_names  = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        queryset = Categoria.objects.annotate(total_chamados=Count("chamados"))
        # Formulário de chamado vê só as ativas; a tela de admin pede ?todas=1.
        user = self.request.user
        ver_todas = self.request.query_params.get("todas") == "1"
        if ver_todas and (user.is_staff or user.is_superuser):
            return queryset
        if self.action in ("list", "retrieve"):
            return queryset.filter(ativa=True)
        return queryset

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [IsAuthenticated()]
        return [IsStaff()]

    def destroy(self, request, *args, **kwargs):
        categoria = self.get_object()
        if categoria.chamados.exists():
            return Response(
                {"detail": "Esta categoria possui chamados vinculados. Desative-a em vez de excluir."},
                status=status.HTTP_409_CONFLICT,
            )
        categoria.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── Chamados ──────────────────────────────────────────────────────────────────

class ChamadoViewSet(viewsets.ModelViewSet):
    serializer_class   = ChamadoSerializer
    permission_classes = [IsAuthenticated]
    http_method_names  = ["get", "post", "patch", "head", "options"]
    # IDs somente numericos, inclusive nas rotas aninhadas: texto na URL vira 404, nao erro 500.
    lookup_value_regex = r"\d+"

    def get_queryset(self):
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return Chamado.objects.select_related("usuario", "categoria").all()
        return Chamado.objects.select_related("usuario", "categoria").filter(usuario=user)

    def get_permissions(self):
        if self.action in ("partial_update", "cancelar"):
            return [IsStaff()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        # Staff pode abrir o chamado em nome de outro usuario enviando "solicitante" (id).
        usuario = self.request.user
        solicitante = self.request.data.get("solicitante")
        if solicitante not in (None, ""):
            if not (usuario.is_staff or usuario.is_superuser):
                raise PermissionDenied("Somente a equipe pode abrir chamados em nome de outro usuário.")
            try:
                usuario = User.objects.get(pk=solicitante, is_active=True)
            except (User.DoesNotExist, ValueError, TypeError):
                raise ValidationError({"solicitante": "Usuário inválido."})
        # Todo chamado nasce "aberto", ignorando o status enviado pelo cliente.
        chamado = serializer.save(usuario=usuario, status="aberto")
        if usuario != self.request.user:
            # Aberto pela equipe: o historico aponta o admin como autor e o solicitante e avisado.
            HistoricoChamado.objects.filter(
                chamado=chamado, acao=HistoricoChamado.ACAO_CRIOU
            ).update(autor=self.request.user)
            enviar_notificacao_status_chamado(
                chamado,
                mensagem=f"O chamado #{chamado.id} foi aberto para você pela equipe ({self.request.user.username}).",
            )

    def partial_update(self, request, *args, **kwargs):
        chamado = self.get_object()
        status_anterior = chamado.status
        antes = {"status": chamado.status, "prioridade": chamado.prioridade}

        serializer = self.get_serializer(chamado, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        chamado_atualizado = serializer.save()
        registrar_edicoes(chamado_atualizado, request.user, antes)

        if chamado_atualizado.status != status_anterior:
            enviar_notificacao_status_chamado(chamado_atualizado)

        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def cancelar(self, request, pk=None):
        chamado = self.get_object()
        if chamado.status in ("concluido", "cancelado"):
            return Response(
                {"detail": f"Chamado {chamado.get_status_display().lower()} não pode ser cancelado."},
                status=status.HTTP_409_CONFLICT,
            )
        motivo = _resumo(str(request.data.get("motivo") or "").strip())
        antes = {"status": chamado.status, "prioridade": chamado.prioridade}
        chamado.status = "cancelado"
        chamado.motivo_cancelamento = motivo
        chamado.data_cancelamento = timezone.now()
        chamado.save(update_fields=["status", "motivo_cancelamento", "data_cancelamento"])
        registrar_edicoes(chamado, request.user, antes)
        if motivo:
            HistoricoChamado.objects.create(
                chamado=chamado,
                autor=request.user,
                acao=HistoricoChamado.ACAO_EDITOU,
                atributo="Motivo do cancelamento",
                valor_novo=motivo,
            )
        enviar_notificacao_status_chamado(chamado)
        return Response(self.get_serializer(chamado).data)


# ── Comentários ───────────────────────────────────────────────────────────────

class ComentarioViewSet(viewsets.ModelViewSet):
    serializer_class   = ComentarioSerializer
    permission_classes = [IsAuthenticated]
    http_method_names  = ["get", "post", "head", "options"]

    def get_queryset(self):
        # Cliente so enxerga os comentarios dos proprios chamados.
        user = self.request.user
        comentarios = Comentario.objects.filter(chamado_id=self.kwargs.get("chamado_pk"))
        if not (user.is_staff or user.is_superuser):
            comentarios = comentarios.filter(chamado__usuario=user)
        return comentarios.select_related("usuario")

    def get_permissions(self):
        if self.action == "create":
            return [IsAuthenticated(), IsChamadoOwnerOrStaff()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        chamado_pk = self.kwargs.get("chamado_pk")
        chamado    = get_object_or_404(Chamado, pk=chamado_pk)
        self.check_object_permissions(self.request, chamado)
        serializer.save(chamado=chamado, usuario=self.request.user)


# ── Histórico ─────────────────────────────────────────────────────────────────

class HistoricoViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class   = HistoricoChamadoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Cliente so enxerga o historico dos proprios chamados.
        user = self.request.user
        chamados = Chamado.objects.all()
        if not (user.is_staff or user.is_superuser):
            chamados = chamados.filter(usuario=user)
        return HistoricoChamado.objects.filter(
            chamado_id=self.kwargs.get("chamado_pk"), chamado__in=chamados
        ).select_related("autor")


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
