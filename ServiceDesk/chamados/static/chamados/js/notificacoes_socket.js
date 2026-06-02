(() => {
    // Usa configuracao global definida no template para polling HTTP.
    const endpointNotificacoes = window.NOTIFICACOES_PENDENTES_URL || "";
    const caixaNotificacoes = document.getElementById("caixa-notificacoes");

    // Sai silenciosamente se a pagina nao tiver area de notificacao configurada.
    if (!caixaNotificacoes || !endpointNotificacoes) {
        return;
    }

    function renderizarNotificacao(texto) {
        // Cria alerta Bootstrap simples para exibir mensagem em tempo real.
        const notificacao = document.createElement("div");
        notificacao.className = "alert alert-info shadow-sm mb-2";
        notificacao.style.pointerEvents = "auto";
        notificacao.textContent = texto;
        caixaNotificacoes.prepend(notificacao);

        // Remove automaticamente apos alguns segundos para nao poluir a tela.
        setTimeout(() => {
            notificacao.remove();
        }, 6000);
    }

    async function buscarNotificacoes() {
        try {
            const resposta = await fetch(endpointNotificacoes, {
                credentials: "same-origin",
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                },
            });
            if (!resposta.ok) {
                return;
            }

            const payload = await resposta.json();
            for (const notificacao of payload.notificacoes || []) {
                if (notificacao.mensagem) {
                    renderizarNotificacao(notificacao.mensagem);
                }
            }
        } catch (_) {
            // Falha silenciosa para nao interferir na navegacao da pagina.
        }
    }

    // Consulta imediatamente e continua atualizando periodicamente.
    buscarNotificacoes();
    setInterval(buscarNotificacoes, 5000);
})();
