import json
import logging
import socket

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import (
    AtualizacaoChamadoAdminForm,
    CadastroUsuarioForm,
    ChamadoForm,
    LoginUsuarioForm,
    MensagemChamadoForm,
)
from .models import Chamado, Comentario, Notificacao


# Logger simples para registrar falhas nao bloqueantes de notificacao.
logger = logging.getLogger(__name__)


def _destino_pos_login(request):
    # Evita redirecionamento para URL externa apos login.
    destino = request.POST.get("next") or request.GET.get("next")
    if destino and url_has_allowed_host_and_scheme(
        url=destino,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return destino
    return "lista_chamados"


def enviar_notificacao_status_chamado(chamado):
    # Monta mensagem simples no formato solicitado para notificacao em tempo real.
    mensagem = (
        f"Seu chamado #{chamado.id} foi atualizado para "
        f"{chamado.get_status_display().upper()}"
    )
    payload = {
        "tipo": "status_chamado",
        "chamado_id": chamado.id,
        "usuario_id": chamado.usuario_id,
        "status": chamado.status,
        "mensagem": mensagem,
    }

    # Persiste a notificacao para o frontend recupera-la por polling HTTP.
    Notificacao.objects.create(
        usuario_id=chamado.usuario_id,
        chamado=chamado,
        tipo="status_chamado",
        mensagem=mensagem,
    )

    # Envia o evento para um servidor TCP via socket puro.
    try:
        with socket.create_connection(
            (settings.SOCKET_NOTIFICACAO_HOST, settings.SOCKET_NOTIFICACAO_PORT),
            timeout=0.5,
        ) as cliente_socket:
            envelope = {"acao": "publicar", "payload": payload}
            cliente_socket.sendall(
                (json.dumps(envelope, ensure_ascii=False) + "\n").encode("utf-8")
            )
    except Exception as exc:
        logger.info(
            "Falha ao enviar notificacao para o servidor TCP: %s",
            exc,
        )


def login_usuario(request):
    # Se ja estiver autenticado, volta direto para o painel.
    if request.user.is_authenticated:
        return redirect("lista_chamados")

    if request.method == "POST":
        # AuthenticationForm valida usuario e senha usando o auth do Django (RF02).
        form = LoginUsuarioForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            messages.success(request, "Login realizado com sucesso.")
            return redirect(_destino_pos_login(request))
    else:
        form = LoginUsuarioForm()

    return render(
        request,
        # Template organizado por pasta da rota de login.
        "chamados/login/index.html",
        {"form": form, "next": request.GET.get("next", "")},
    )


def cadastro_usuario(request):
    # Se ja estiver logado, nao precisa cadastrar de novo.
    if request.user.is_authenticated:
        return redirect("lista_chamados")

    if request.method == "POST":
        # Formulario de cadastro do novo usuario (RF01).
        form = CadastroUsuarioForm(request.POST)
        if form.is_valid():
            usuario = form.save()
            # Login automatico apos cadastro para melhorar a experiencia.
            login(request, usuario)
            messages.success(request, "Cadastro realizado com sucesso.")
            return redirect("lista_chamados")
    else:
        form = CadastroUsuarioForm()

    # Template organizado por pasta da rota de cadastro.
    return render(request, "chamados/cadastro/index.html", {"form": form})


@login_required
def logout_usuario(request):
    # Encerra a sessao do usuario atual.
    logout(request)
    messages.info(request, "Sessao encerrada.")
    return redirect("login_usuario")


@login_required
def criar_chamado(request):
    # Fluxo de criacao do chamado:
    # - GET: exibe formulario vazio
    # - POST: valida dados e salva no banco
    if request.method == "POST":
        form = ChamadoForm(request.POST)
        if form.is_valid():
            # commit=False permite complementar campos antes de salvar.
            chamado = form.save(commit=False)
            # Vincula o chamado ao usuario autenticado.
            chamado.usuario = request.user
            chamado.save()
            messages.success(request, "Chamado registrado com sucesso.")
            # Cliente segue direto para a area de acompanhamento do proprio chamado.
            if request.user.is_staff or request.user.is_superuser:
                return redirect("lista_chamados")
            return redirect("historico_chamados_cliente")
    else:
        # Primeira abertura da pagina (sem envio de dados).
        form = ChamadoForm()

    # Renderiza a pagina de abertura de chamado.
    # Template organizado por pasta da rota de novo chamado.
    return render(request, "chamados/novo/index.html", {"form": form})


@login_required
def lista_chamados(request):
    # Regra de negocio:
    # - staff (tecnico/admin) enxerga todos os chamados no painel
    # - cliente ve um resumo dos proprios chamados na home
    if request.user.is_staff or request.user.is_superuser:
        # Lista geral de chamados para acompanhamento inicial do time de infra.
        chamados = Chamado.objects.all()
        total_chamados_cliente = 0
    else:
        # Home do cliente mostra apenas os chamados mais recentes dele.
        chamados = Chamado.objects.filter(usuario=request.user)[:5]
        total_chamados_cliente = Chamado.objects.filter(usuario=request.user).count()

    # Envia a lista para o template do painel.
    # Template organizado por pasta da rota principal do painel.
    return render(
        request,
        "chamados/lista/index.html",
        {
            "chamados": chamados,
            "total_chamados_cliente": total_chamados_cliente,
        },
    )


@login_required
def detalhe_chamado_admin(request, chamado_id):
    # Apenas equipe de infra (staff/admin) pode acessar o detalhe operacional do chamado.
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, "Somente a equipe de infra pode visualizar este chamado.")
        return redirect("lista_chamados")

    # Busca o chamado com comentarios e usuario para exibir historico completo na tela dedicada.
    chamado = get_object_or_404(
        Chamado.objects.select_related("usuario").prefetch_related("comentarios__usuario"),
        id=chamado_id,
    )
    # Formulario inicial para atualizar status/prioridade e responder o chamado.
    form_atualizacao = AtualizacaoChamadoAdminForm(chamado=chamado)
    return render(
        request,
        # Template organizado por pasta da rota de detalhe do chamado.
        "chamados/detalhe_chamado/index.html",
        {"chamado": chamado, "form_atualizacao": form_atualizacao},
    )


@login_required
def atualizar_chamado_admin(request, chamado_id):
    # Apenas equipe de infra (staff/admin) pode atualizar status, prioridade e resposta.
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, "Somente a equipe de infra pode atualizar chamados.")
        return redirect("lista_chamados")

    # Recupera o chamado selecionado para atualizar os dados de atendimento.
    chamado = get_object_or_404(Chamado, id=chamado_id)
    if request.method != "POST":
        return redirect("detalhe_chamado_admin", chamado_id=chamado.id)

    # Valida os dados enviados no formulario de atendimento da tela de detalhe.
    form = AtualizacaoChamadoAdminForm(request.POST, chamado=chamado)
    if not form.is_valid():
        messages.error(request, "Nao foi possivel atualizar o chamado.")
        return redirect("detalhe_chamado_admin", chamado_id=chamado.id)

    # Guarda status anterior para notificar somente quando houver mudanca real.
    status_anterior = chamado.status

    # Salva as alteracoes operacionais feitas pela equipe de infra.
    chamado.status = form.cleaned_data["status"]
    chamado.prioridade = form.cleaned_data["prioridade"]
    chamado.save(update_fields=["status", "prioridade"])

    # Registra resposta textual no historico quando preenchida.
    resposta = form.cleaned_data["resposta"].strip()
    if resposta:
        Comentario.objects.create(
            chamado=chamado,
            usuario=request.user,
            texto=resposta,
        )

    # Dispara notificacao em tempo real para o usuario dono do chamado.
    if status_anterior != chamado.status:
        enviar_notificacao_status_chamado(chamado)

    messages.success(request, "Chamado atualizado com sucesso.")
    return redirect("detalhe_chamado_admin", chamado_id=chamado.id)


@login_required
def detalhe_chamado_cliente(request, chamado_id):
    # Cliente acessa apenas o proprio chamado para acompanhar e conversar com a equipe.
    if request.user.is_staff or request.user.is_superuser:
        messages.info(request, "Esta tela de conversa e destinada ao perfil cliente.")
        return redirect("detalhe_chamado_admin", chamado_id=chamado_id)

    chamado = get_object_or_404(
        Chamado.objects.select_related("usuario").prefetch_related("comentarios__usuario"),
        id=chamado_id,
        usuario=request.user,
    )

    form_mensagem = MensagemChamadoForm()
    return render(
        request,
        "chamados/detalhe_cliente/index.html",
        {"chamado": chamado, "form_mensagem": form_mensagem},
    )


@login_required
def responder_chamado_cliente(request, chamado_id):
    # Cliente pode responder somente dentro dos proprios chamados.
    if request.user.is_staff or request.user.is_superuser:
        messages.error(request, "A conversa do cliente nao esta disponivel para administradores.")
        return redirect("lista_chamados")

    chamado = get_object_or_404(Chamado, id=chamado_id, usuario=request.user)
    if request.method != "POST":
        return redirect("detalhe_chamado_cliente", chamado_id=chamado.id)

    form = MensagemChamadoForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Nao foi possivel enviar sua mensagem.")
        return redirect("detalhe_chamado_cliente", chamado_id=chamado.id)

    Comentario.objects.create(
        chamado=chamado,
        usuario=request.user,
        texto=form.cleaned_data["mensagem"].strip(),
    )
    messages.success(request, "Mensagem enviada para a equipe.")
    return redirect("detalhe_chamado_cliente", chamado_id=chamado.id)


@login_required
def historico_chamados_cliente(request):
    # Esta tela foi criada para o perfil cliente consultar somente os proprios chamados.
    if request.user.is_staff or request.user.is_superuser:
        # Perfil admin continua no painel principal de acompanhamento geral.
        messages.info(
            request,
            "O historico individual e destinado ao perfil cliente.",
        )
        return redirect("lista_chamados")

    # Filtro de seguranca: retorna apenas os chamados do usuario autenticado.
    chamados = Chamado.objects.filter(usuario=request.user)
    # Renderiza a nova pagina de historico individual.
    return render(
        request,
        # Template organizado por pasta da rota de historico do cliente.
        "chamados/meus_chamados/index.html",
        {"chamados": chamados},
    )


@login_required
def notificacoes_pendentes(request):
    # Entrega apenas as notificacoes do usuario logado para evitar consumir notificacoes de outros.
    consulta = Notificacao.objects.select_related("chamado", "usuario").filter(
        lida=False, usuario=request.user
    )

    notificacoes = list(consulta.order_by("criada_em", "id")[:20])
    payload = [
        {
            "id": notificacao.id,
            "tipo": notificacao.tipo,
            "chamado_id": notificacao.chamado_id,
            "usuario_id": notificacao.usuario_id,
            "mensagem": notificacao.mensagem,
            "criada_em": notificacao.criada_em.isoformat(),
        }
        for notificacao in notificacoes
    ]

    if notificacoes:
        Notificacao.objects.filter(id__in=[item.id for item in notificacoes]).update(lida=True)

    return JsonResponse({"notificacoes": payload})
