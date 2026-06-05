from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from urllib.parse import parse_qs, urlparse
from unittest import mock

from .models import Chamado, Comentario, Notificacao


class FluxoAutenticacaoTests(TestCase):
    def test_cadastro_cria_usuario_e_autentica(self):
        # RF01: novo usuario deve conseguir se cadastrar na plataforma.
        response = self.client.post(
            reverse("cadastro_usuario"),
            {
                "username": "ana",
                "first_name": "Ana",
                "last_name": "Silva",
                "email": "ana@example.com",
                "password1": "SenhaForte123!",
                "password2": "SenhaForte123!",
            },
        )

        self.assertRedirects(response, reverse("lista_chamados"))
        self.assertTrue(User.objects.filter(username="ana").exists())

    def test_login_autentica_usuario_existente(self):
        # RF02: usuario cadastrado deve conseguir fazer login.
        User.objects.create_user(username="bruno", password="SenhaForte123!")

        response = self.client.post(
            reverse("login_usuario"),
            {"username": "bruno", "password": "SenhaForte123!"},
        )

        self.assertRedirects(response, reverse("lista_chamados"))

    def test_login_autentica_com_email(self):
        # RF02: usuario cadastrado tambem deve conseguir fazer login com o e-mail.
        User.objects.create_user(
            username="bruno",
            email="bruno@example.com",
            password="SenhaForte123!",
        )

        response = self.client.post(
            reverse("login_usuario"),
            {"username": "bruno@example.com", "password": "SenhaForte123!"},
        )

        self.assertRedirects(response, reverse("lista_chamados"))

    def test_rotas_protegidas_redirecionam_para_login(self):
        # Garantia de seguranca: sem login, o usuario nao acessa painel, novo chamado e historico.
        response_lista = self.client.get(reverse("lista_chamados"))
        response_novo = self.client.get(reverse("criar_chamado"))
        # Nova rota de historico individual tambem fica protegida por autenticacao.
        response_historico = self.client.get(reverse("historico_chamados_cliente"))

        self.assertEqual(response_lista.status_code, 302)
        self.assertIn(reverse("login_usuario"), response_lista.url)
        self.assertEqual(response_novo.status_code, 302)
        self.assertIn(reverse("login_usuario"), response_novo.url)
        self.assertEqual(response_historico.status_code, 302)
        self.assertIn(reverse("login_usuario"), response_historico.url)

    @override_settings(GOOGLE_OAUTH_ENABLED=False)
    def test_login_google_sem_configuracao_redireciona_para_login(self):
        response = self.client.get("/accounts/google/login/", follow=True)

        self.assertRedirects(response, reverse("login_usuario"))
        self.assertContains(
            response,
            "Login com Google ainda nao foi configurado neste ambiente.",
        )

    @override_settings(
        FRONTEND_GOOGLE_CALLBACK_URL="http://localhost:5500/pages/auth/google-callback/index.html"
    )
    def test_sucesso_google_entrega_tokens_para_frontend(self):
        User.objects.create_user(
            username="google_user",
            email="google@example.com",
            password="SenhaForte123!",
        )
        self.client.login(username="google_user", password="SenhaForte123!")

        response = self.client.get(reverse("api_google_success"))
        destino = response["Location"]
        url = urlparse(destino)
        fragmento = parse_qs(url.fragment)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            f"{url.scheme}://{url.netloc}{url.path}",
            "http://localhost:5500/pages/auth/google-callback/index.html",
        )
        self.assertIn("access", fragmento)
        self.assertIn("refresh", fragmento)
        self.assertIn("user", fragmento)


class ChamadosTests(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_user(username="cliente", password="SenhaForte123!")
        self.outro_usuario = User.objects.create_user(
            username="outro", password="SenhaForte123!"
        )
        self.staff = User.objects.create_user(
            username="tecnico", password="SenhaForte123!", is_staff=True
        )

    def test_usuario_comum_nao_visualiza_painel_admin_na_home(self):
        # Perfil cliente nao deve ver painel administrativo na tela inicial.
        Chamado.objects.create(
            titulo="Meu chamado recente",
            descricao="Descricao recente",
            categoria="software",
            prioridade="baixa",
            usuario=self.usuario,
        )
        self.client.login(username="cliente", password="SenhaForte123!")
        response = self.client.get(reverse("lista_chamados"))

        # Valida que o cliente recebe os cards de acao, o resumo dos proprios chamados e nao o painel admin.
        self.assertContains(response, "historico de chamados")
        self.assertContains(response, "Meus chamados recentes")
        self.assertContains(response, "Meu chamado recente")
        self.assertNotContains(response, "Painel de chamados")

    def test_usuario_comum_visualiza_apenas_proprios_chamados_no_historico(self):
        # Historico do cliente deve conter somente chamados dele.
        Chamado.objects.create(
            titulo="Chamado do cliente",
            descricao="Descricao A",
            categoria="software",
            prioridade="baixa",
            usuario=self.usuario,
        )
        Chamado.objects.create(
            titulo="Chamado de outro usuario",
            descricao="Descricao B",
            categoria="hardware",
            prioridade="media",
            usuario=self.outro_usuario,
        )

        self.client.login(username="cliente", password="SenhaForte123!")
        # Nova rota de historico individual do cliente.
        response = self.client.get(reverse("historico_chamados_cliente"))

        self.assertContains(response, "Chamado do cliente")
        self.assertNotContains(response, "Chamado de outro usuario")

    def test_cliente_abre_detalhe_do_proprio_chamado_com_conversa(self):
        # Cliente deve conseguir abrir uma tela dedicada para acompanhar a conversa do chamado.
        chamado = Chamado.objects.create(
            titulo="Portal indisponivel",
            descricao="Nao consigo acessar o portal.",
            categoria="software",
            prioridade="media",
            usuario=self.usuario,
        )
        Comentario.objects.create(
            chamado=chamado,
            usuario=self.staff,
            texto="Estamos analisando o caso.",
        )

        self.client.login(username="cliente", password="SenhaForte123!")
        response = self.client.get(reverse("detalhe_chamado_cliente", args=[chamado.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Conversa com a equipe")
        self.assertContains(response, "Estamos analisando o caso.")

    def test_cliente_nao_abre_chamado_de_outro_usuario(self):
        # Cliente nao pode acessar conversa de chamado que nao pertence a ele.
        chamado = Chamado.objects.create(
            titulo="Chamado restrito",
            descricao="Descricao privada.",
            categoria="rede",
            prioridade="baixa",
            usuario=self.outro_usuario,
        )

        self.client.login(username="cliente", password="SenhaForte123!")
        response = self.client.get(reverse("detalhe_chamado_cliente", args=[chamado.id]))

        self.assertEqual(response.status_code, 404)

    def test_cliente_envia_mensagem_para_equipe(self):
        # Cliente deve conseguir responder no proprio chamado para manter a conversa.
        chamado = Chamado.objects.create(
            titulo="Acesso bloqueado",
            descricao="Nao consigo entrar no sistema.",
            categoria="acesso",
            prioridade="alta",
            usuario=self.usuario,
        )

        self.client.login(username="cliente", password="SenhaForte123!")
        response = self.client.post(
            reverse("responder_chamado_cliente", args=[chamado.id]),
            {"mensagem": "Consegue verificar ainda hoje?"},
        )

        self.assertRedirects(response, reverse("detalhe_chamado_cliente", args=[chamado.id]))
        self.assertTrue(
            Comentario.objects.filter(
                chamado=chamado,
                usuario=self.usuario,
                texto="Consegue verificar ainda hoje?",
            ).exists()
        )

    def test_staff_e_redirecionado_ao_tentar_abrir_historico_cliente(self):
        # Rotina evita que admin use a tela exclusiva de historico do cliente.
        self.client.login(username="tecnico", password="SenhaForte123!")
        response = self.client.get(reverse("historico_chamados_cliente"))

        self.assertRedirects(response, reverse("lista_chamados"))

    def test_staff_visualiza_todos_os_chamados(self):
        # RF04: perfil tecnico/admin pode acompanhar todos os chamados.
        Chamado.objects.create(
            titulo="Chamado A",
            descricao="Descricao A",
            categoria="rede",
            prioridade="alta",
            status="aberto",
            usuario=self.usuario,
        )
        Chamado.objects.create(
            titulo="Chamado B",
            descricao="Descricao B",
            categoria="acesso",
            prioridade="media",
            status="andamento",
            usuario=self.outro_usuario,
        )

        self.client.login(username="tecnico", password="SenhaForte123!")
        response = self.client.get(reverse("lista_chamados"))

        self.assertContains(response, "Chamado A")
        self.assertContains(response, "Chamado B")
        # RF05: status deve aparecer no painel para acompanhamento.
        self.assertContains(response, "Em andamento")

    def test_staff_visualiza_detalhe_em_rota_dedicada(self):
        # Visualizacao de chamado para equipe de infra deve ocorrer em pagina propria.
        chamado = Chamado.objects.create(
            titulo="Chamado detalhe",
            descricao="Descricao para pagina dedicada.",
            categoria="software",
            prioridade="media",
            status="aberto",
            usuario=self.usuario,
        )

        self.client.login(username="tecnico", password="SenhaForte123!")
        response = self.client.get(reverse("detalhe_chamado_admin", args=[chamado.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Chamado detalhe")
        self.assertContains(response, "Atualizar atendimento")

    def test_staff_visualiza_mensagens_do_cliente_no_detalhe(self):
        # Equipe deve enxergar tambem as mensagens enviadas pelo cliente.
        chamado = Chamado.objects.create(
            titulo="Erro no sistema",
            descricao="Falha ao abrir tela.",
            categoria="software",
            prioridade="media",
            status="aberto",
            usuario=self.usuario,
        )
        Comentario.objects.create(
            chamado=chamado,
            usuario=self.usuario,
            texto="Consigo reproduzir o problema em dois computadores.",
        )

        self.client.login(username="tecnico", password="SenhaForte123!")
        response = self.client.get(reverse("detalhe_chamado_admin", args=[chamado.id]))

        self.assertContains(response, "Conversa do chamado")
        self.assertContains(response, "Consigo reproduzir o problema em dois computadores.")

    def test_cliente_nao_pode_visualizar_detalhe_admin(self):
        # Cliente deve ser bloqueado ao tentar abrir rota de detalhe administrativo.
        chamado = Chamado.objects.create(
            titulo="Restrito admin",
            descricao="Somente equipe de infra.",
            categoria="rede",
            prioridade="baixa",
            status="aberto",
            usuario=self.usuario,
        )

        self.client.login(username="cliente", password="SenhaForte123!")
        response = self.client.get(reverse("detalhe_chamado_admin", args=[chamado.id]))

        self.assertRedirects(response, reverse("lista_chamados"))

    @mock.patch("chamados.views.socket.create_connection")
    def test_staff_atualiza_status_prioridade_e_registra_resposta(self, mock_create_connection):
        # Equipe de infra pode atualizar atendimento e registrar resposta tecnica.
        mock_socket = mock.MagicMock()
        mock_create_connection.return_value.__enter__.return_value = mock_socket

        chamado = Chamado.objects.create(
            titulo="Erro no e-mail",
            descricao="Caixa postal indisponivel.",
            categoria="acesso",
            prioridade="baixa",
            status="aberto",
            usuario=self.usuario,
        )

        self.client.login(username="tecnico", password="SenhaForte123!")
        response = self.client.post(
            reverse("atualizar_chamado_admin", args=[chamado.id]),
            {
                "status": "concluido",
                "prioridade": "alta",
                "resposta": "Conta revisada e servico normalizado.",
            },
        )

        self.assertRedirects(response, reverse("detalhe_chamado_admin", args=[chamado.id]))
        chamado.refresh_from_db()
        self.assertEqual(chamado.status, "concluido")
        self.assertEqual(chamado.prioridade, "alta")
        self.assertTrue(
            Comentario.objects.filter(
                chamado=chamado,
                usuario=self.staff,
                texto="Conta revisada e servico normalizado.",
            ).exists()
        )
        self.assertTrue(
            Notificacao.objects.filter(
                chamado=chamado,
                usuario=self.usuario,
                tipo="status_chamado",
            ).exists()
        )

    @mock.patch("chamados.views.socket.create_connection", side_effect=OSError("socket indisponivel"))
    def test_staff_sem_socket_nao_salva_notificacao(self, _mock_create_connection):
        # Se o servidor TCP nao estiver disponivel, a notificacao nao deve ser persistida.
        chamado = Chamado.objects.create(
            titulo="Sem notificacao",
            descricao="Teste de falha do socket.",
            categoria="software",
            prioridade="media",
            status="aberto",
            usuario=self.usuario,
        )

        self.client.login(username="tecnico", password="SenhaForte123!")
        response = self.client.post(
            reverse("atualizar_chamado_admin", args=[chamado.id]),
            {
                "status": "concluido",
                "prioridade": "alta",
                "resposta": "Atualizacao feita, mas sem socket.",
            },
        )

        self.assertRedirects(response, reverse("detalhe_chamado_admin", args=[chamado.id]))
        self.assertFalse(
            Notificacao.objects.filter(
                chamado=chamado,
                usuario=self.usuario,
                tipo="status_chamado",
            ).exists()
        )

    def test_cliente_nao_pode_atualizar_chamado_admin(self):
        # Cliente nao pode alterar status/prioridade nem responder como infra.
        chamado = Chamado.objects.create(
            titulo="Sem internet",
            descricao="Rede indisponivel.",
            categoria="rede",
            prioridade="media",
            status="aberto",
            usuario=self.usuario,
        )

        self.client.login(username="cliente", password="SenhaForte123!")
        response = self.client.post(
            reverse("atualizar_chamado_admin", args=[chamado.id]),
            {
                "status": "concluido",
                "prioridade": "alta",
                "resposta": "Tentativa invalida de atualizacao.",
            },
        )

        self.assertRedirects(response, reverse("lista_chamados"))
        chamado.refresh_from_db()
        self.assertEqual(chamado.status, "aberto")
        self.assertEqual(chamado.prioridade, "media")
        self.assertFalse(Comentario.objects.filter(chamado=chamado).exists())

    def test_endpoint_de_notificacoes_entrega_e_marca_como_lida(self):
        # Polling deve retornar notificacoes pendentes do cliente e marca-las como lidas.
        chamado = Chamado.objects.create(
            titulo="Troca de status",
            descricao="Descricao",
            categoria="software",
            prioridade="media",
            status="andamento",
            usuario=self.usuario,
        )
        notificacao = Notificacao.objects.create(
            usuario=self.usuario,
            chamado=chamado,
            tipo="status_chamado",
            mensagem="Seu chamado foi atualizado.",
        )

        self.client.login(username="cliente", password="SenhaForte123!")
        response = self.client.get(reverse("notificacoes_pendentes"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["notificacoes"][0]["id"], notificacao.id)
        notificacao.refresh_from_db()
        self.assertTrue(notificacao.lida)

        response_vazio = self.client.get(reverse("notificacoes_pendentes"))
        self.assertEqual(response_vazio.json()["notificacoes"], [])

    def test_registro_de_chamado_salva_categoria(self):
        # RF03: registro inclui titulo, descricao e categoria.
        self.client.login(username="cliente", password="SenhaForte123!")
        response = self.client.post(
            reverse("criar_chamado"),
            {
                "titulo": "Sem acesso ao sistema",
                "descricao": "Nao consigo entrar com meu usuario.",
                "categoria": "acesso",
                "prioridade": "alta",
            },
        )

        self.assertRedirects(response, reverse("historico_chamados_cliente"))
        chamado = Chamado.objects.get(titulo="Sem acesso ao sistema")
        self.assertEqual(chamado.categoria, "acesso")
        self.assertEqual(chamado.status, "aberto")
        self.assertEqual(chamado.usuario, self.usuario)

    def test_staff_ao_criar_chamado_retorna_para_painel_admin(self):
        # Fluxo administrativo continua no painel principal apos abrir chamado.
        self.client.login(username="tecnico", password="SenhaForte123!")
        response = self.client.post(
            reverse("criar_chamado"),
            {
                "titulo": "Chamado interno",
                "descricao": "Criado pelo tecnico.",
                "categoria": "hardware",
                "prioridade": "media",
            },
        )

        self.assertRedirects(response, reverse("lista_chamados"))
