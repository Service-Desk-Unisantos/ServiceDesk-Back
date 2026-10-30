from django.urls import path
from rest_framework_nested import routers
from rest_framework_simplejwt.views import TokenBlacklistView, TokenRefreshView

from .views import (
    CadastroView,
    CategoriaViewSet,
    ChamadoViewSet,
    ComentarioViewSet,
    HistoricoViewSet,
    LoginView,
    NotificacaoViewSet,
)

router = routers.DefaultRouter()
router.register("categorias",   CategoriaViewSet,   basename="categoria")
router.register("chamados",     ChamadoViewSet,     basename="chamado")
router.register("notificacoes", NotificacaoViewSet, basename="notificacao")

chamados_router = routers.NestedDefaultRouter(router, "chamados", lookup="chamado")
chamados_router.register("comentarios", ComentarioViewSet, basename="chamado-comentarios")
chamados_router.register("historico",   HistoricoViewSet,  basename="chamado-historico")

urlpatterns = [
    path("auth/login/",    LoginView.as_view(),        name="api_login"),
    path("auth/logout/",   TokenBlacklistView.as_view(), name="api_logout"),
    path("auth/refresh/",  TokenRefreshView.as_view(),  name="api_refresh"),
    path("auth/cadastro/", CadastroView.as_view(),      name="api_cadastro"),
    *router.urls,
    *chamados_router.urls,
]
