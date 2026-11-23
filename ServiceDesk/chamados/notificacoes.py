import json
import logging
import socket

from django.conf import settings

from .models import Notificacao

# Logger simples para registrar falhas nao bloqueantes de notificacao.
logger = logging.getLogger(__name__)


def enviar_notificacao_status_chamado(chamado, mensagem=None):
    # Monta mensagem simples no formato solicitado para notificacao em tempo real.
    mensagem = mensagem or (
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
        return

    # Persiste a notificacao somente quando o servidor TCP respondeu com sucesso.
    Notificacao.objects.create(
        usuario_id=chamado.usuario_id,
        chamado=chamado,
        tipo="status_chamado",
        mensagem=mensagem,
    )
