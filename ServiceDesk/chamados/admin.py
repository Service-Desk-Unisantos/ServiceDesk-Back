from django.contrib import admin

from .models import Categoria, Chamado, Comentario, HistoricoChamado, Notificacao


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    # Categorias oferecidas na abertura de chamado; inativas ficam ocultas no formulario.
    list_display = ("id", "nome", "slug", "ativa")
    list_filter = ("ativa",)
    search_fields = ("nome",)


@admin.register(Chamado)
class ChamadoAdmin(admin.ModelAdmin):
    # Campos principais no painel admin para acompanhamento dos chamados.
    list_display = ("id", "titulo", "categoria", "prioridade", "status", "usuario", "data_criacao")
    list_select_related = ("categoria", "usuario")
    list_filter = ("categoria", "prioridade", "status", "data_criacao")
    search_fields = ("titulo", "descricao", "usuario__username")
    ordering = ("-data_criacao",)


@admin.register(Comentario)
class ComentarioAdmin(admin.ModelAdmin):
    # Facilita localizar comentarios vinculados aos chamados.
    list_display = ("id", "chamado", "usuario", "data")
    list_filter = ("data",)
    search_fields = ("texto", "usuario__username", "chamado__titulo")


@admin.register(Notificacao)
class NotificacaoAdmin(admin.ModelAdmin):
    # Exibe notificacoes persistidas para auditoria do fluxo de status.
    list_display = ("id", "tipo", "usuario", "chamado", "lida", "criada_em")
    list_filter = ("tipo", "lida", "criada_em")
    search_fields = ("mensagem", "usuario__username", "chamado__titulo")


@admin.register(HistoricoChamado)
class HistoricoChamadoAdmin(admin.ModelAdmin):
    list_display = ("id", "chamado", "autor", "acao", "atributo", "data")
    list_filter = ("acao", "atributo", "data")
    search_fields = ("chamado__titulo", "autor__username", "valor_novo")
