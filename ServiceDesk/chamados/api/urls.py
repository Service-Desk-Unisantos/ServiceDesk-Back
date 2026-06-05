from django.urls import path
from rest_framework_nested import routers
from rest_framework_simplejwt.views import TokenBlacklistView, TokenRefreshView

from .views import (
    CadastroView,
    ChamadoViewSet,
    ComentarioViewSet,
    LoginView,
    NotificacaoViewSet,
    google_auth_success,
)

router = routers.DefaultRouter()
router.register("chamados",     ChamadoViewSet,     basename="chamado")
router.register("notificacoes", NotificacaoViewSet, basename="notificacao")

chamados_router = routers.NestedDefaultRouter(router, "chamados", lookup="chamado")
chamados_router.register("comentarios", ComentarioViewSet, basename="chamado-comentarios")

urlpatterns = [
    path("auth/login/",    LoginView.as_view(),        name="api_login"),
    path("auth/logout/",   TokenBlacklistView.as_view(), name="api_logout"),
    path("auth/refresh/",  TokenRefreshView.as_view(),  name="api_refresh"),
    path("auth/cadastro/", CadastroView.as_view(),      name="api_cadastro"),
    path("auth/google/success/", google_auth_success, name="api_google_success"),
    *router.urls,
    *chamados_router.urls,
]
