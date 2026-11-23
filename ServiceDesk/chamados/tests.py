from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from urllib.parse import parse_qs, urlparse
from unittest import mock

from rest_framework.test import APIClient

from .models import Categoria, Chamado, Comentario, Notificacao
from .notificacoes import enviar_notificacao_status_chamado


class FluxoAutenticacaoTests(TestCase):
    def setUp(self):
        self.api = APIClient()

    def test_cadastro_cria_usuario_e_devolve_tokens(self):
        # RF01: novo usuario deve conseguir se cadastrar na plataforma.
        response = self.api.post(
            "/api/v1/auth/cadastro/",
            {
                "username": "ana",
                "first_name": "Ana",
                "last_name": "Silva",
                "email": "ana@example.com",
                "password1": "SenhaForte123!",
                "password2": "SenhaForte123!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertIn("access", response.json())
        self.assertIn("refresh", response.json())
        self.assertTrue(User.objects.filter(username="ana").exists())

    def test_login_autentica_usuario_existente(self):
        # RF02: usuario cadastrado deve conseguir fazer login.
        User.objects.create_user(username="bruno", password="SenhaForte123!")

        response = self.api.post(
            "/api/v1/auth/login/",
            {"username": "bruno", "password": "SenhaForte123!"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.json())

    def test_login_autentica_com_email(self):
        # RF02: usuario cadastrado tambem deve conseguir fazer login com o e-mail.
        User.objects.create_user(
            username="bruno",
            email="bruno@example.com",
            password="SenhaForte123!",
        )

        response = self.api.post(
            "/api/v1/auth/login/",
            {"username": "bruno@example.com", "password": "SenhaForte123!"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.json())

    def test_login_com_senha_incorreta_e_recusado(self):
        User.objects.create_user(username="bruno", password="SenhaForte123!")

        response = self.api.post(
            "/api/v1/auth/login/",
            {"username": "bruno", "password": "errada"},
            format="json",
        )

        self.assertEqual(response.status_code, 401)

    def test_rotas_protegidas_exigem_autenticacao(self):
        # Garantia de seguranca: sem token, a API nao entrega chamados nem notificacoes.
        self.assertEqual(self.api.get("/api/v1/chamados/").status_code, 401)
        self.assertEqual(self.api.get("/api/v1/notificacoes/").status_code, 401)

    def test_backend_nao_serve_mais_paginas_html(self):
        # A interface fica no repositorio Frontend; o backend so expoe API, admin e login social.
        self.assertEqual(self.client.get("/").status_code, 404)
        self.assertEqual(self.client.get("/login/").status_code, 404)

    @override_settings(
        GOOGLE_OAUTH_ENABLED=False,
        FRONTEND_LOGIN_URL="http://localhost:5500/pages/login/index.html",
    )
    def test_login_google_sem_configuracao_volta_para_login_do_frontend(self):
        response = self.client.get("/accounts/google/login/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            "http://localhost:5500/pages/login/index.html?google_error=1",
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

        response = self.client.get("/api/v1/auth/google/success/")
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


class ChamadosApiTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.usuario = User.objects.create_user(username="cliente", password="SenhaForte123!")
        self.outro_usuario = User.objects.create_user(
            username="outro", password="SenhaForte123!"
        )
        self.staff = User.objects.create_user(
            username="tecnico", password="SenhaForte123!", is_staff=True
        )

    def _chamado(self, usuario=None, **extra):
        dados = {
            "titulo": "Sem internet",
            "descricao": "Rede indisponivel.",
            "categoria_id": "rede",
            "prioridade": "media",
            "status": "aberto",
            "usuario": usuario or self.usuario,
        }
        dados.update(extra)
        return Chamado.objects.create(**dados)

    def test_cliente_lista_apenas_os_proprios_chamados(self):
        proprio = self._chamado(titulo="Meu chamado")
        self._chamado(usuario=self.outro_usuario, titulo="Chamado de outro")
        self.api.force_authenticate(self.usuario)

        response = self.api.get("/api/v1/chamados/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([c["id"] for c in response.json()["results"]], [proprio.id])

    def test_staff_lista_todos_os_chamados(self):
        self._chamado(titulo="Meu chamado")
        self._chamado(usuario=self.outro_usuario, titulo="Chamado de outro")
        self.api.force_authenticate(self.staff)

        response = self.api.get("/api/v1/chamados/")

        self.assertEqual(response.json()["count"], 2)

    def test_cliente_abre_detalhe_do_proprio_chamado(self):
        chamado = self._chamado()
        self.api.force_authenticate(self.usuario)

        response = self.api.get(f"/api/v1/chamados/{chamado.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["titulo"], "Sem internet")

    def test_cliente_nao_abre_chamado_de_outro_usuario(self):
        chamado = self._chamado(usuario=self.outro_usuario)
        self.api.force_authenticate(self.usuario)

        response = self.api.get(f"/api/v1/chamados/{chamado.id}/")

        self.assertEqual(response.status_code, 404)

    def test_registro_de_chamado_salva_categoria(self):
        # RF03: registro inclui titulo, descricao e categoria.
        self.api.force_authenticate(self.usuario)

        response = self.api.post(
            "/api/v1/chamados/",
            {
                "titulo": "Sem acesso ao sistema",
                "descricao": "Nao consigo entrar com meu usuario.",
                "categoria": "acesso",
                "prioridade": "alta",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        chamado = Chamado.objects.get(titulo="Sem acesso ao sistema")
        self.assertEqual(chamado.categoria_id, "acesso")
        self.assertEqual(chamado.status, "aberto")
        self.assertEqual(chamado.usuario, self.usuario)

    def test_cliente_envia_mensagem_no_proprio_chamado(self):
        chamado = self._chamado()
        self.api.force_authenticate(self.usuario)

        response = self.api.post(
            f"/api/v1/chamados/{chamado.id}/comentarios/",
            {"texto": "Ainda sem conexao."},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            Comentario.objects.filter(chamado=chamado, usuario=self.usuario).exists()
        )

    def test_cliente_nao_comenta_em_chamado_de_outro_usuario(self):
        chamado = self._chamado(usuario=self.outro_usuario)
        self.api.force_authenticate(self.usuario)

        response = self.api.post(
            f"/api/v1/chamados/{chamado.id}/comentarios/",
            {"texto": "Tentativa indevida."},
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Comentario.objects.filter(chamado=chamado).exists())

    @mock.patch("chamados.notificacoes.socket.create_connection")
    def test_staff_atualiza_status_prioridade_e_notifica_cliente(self, mock_create_connection):
        # Equipe de infra atualiza o atendimento e o cliente recebe a notificacao.
        mock_socket = mock.MagicMock()
        mock_create_connection.return_value.__enter__.return_value = mock_socket
        chamado = self._chamado(categoria_id="acesso", prioridade="baixa")
        self.api.force_authenticate(self.staff)

        response = self.api.patch(
            f"/api/v1/chamados/{chamado.id}/",
            {"status": "concluido", "prioridade": "alta"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        chamado.refresh_from_db()
        self.assertEqual(chamado.status, "concluido")
        self.assertEqual(chamado.prioridade, "alta")
        self.assertTrue(
            Notificacao.objects.filter(
                chamado=chamado, usuario=self.usuario, tipo="status_chamado"
            ).exists()
        )

    @mock.patch(
        "chamados.notificacoes.socket.create_connection",
        side_effect=OSError("socket indisponivel"),
    )
    def test_staff_sem_socket_nao_salva_notificacao(self, _mock_create_connection):
        # Se o servidor TCP nao estiver disponivel, a notificacao nao deve ser persistida.
        chamado = self._chamado(categoria_id="software")
        self.api.force_authenticate(self.staff)

        response = self.api.patch(
            f"/api/v1/chamados/{chamado.id}/", {"status": "concluido"}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            Notificacao.objects.filter(
                chamado=chamado, usuario=self.usuario, tipo="status_chamado"
            ).exists()
        )

    @mock.patch("chamados.notificacoes.socket.create_connection")
    def test_notificacao_aceita_mensagem_personalizada(self, mock_create_connection):
        mock_create_connection.return_value.__enter__.return_value = mock.MagicMock()
        chamado = self._chamado()

        enviar_notificacao_status_chamado(chamado, mensagem="Mensagem sob medida")

        self.assertTrue(
            Notificacao.objects.filter(chamado=chamado, mensagem="Mensagem sob medida").exists()
        )

    @mock.patch("chamados.notificacoes.socket.create_connection")
    def test_staff_abre_chamado_para_outro_usuario_e_notifica(self, mock_create_connection):
        mock_create_connection.return_value.__enter__.return_value = mock.MagicMock()
        self.api.force_authenticate(self.staff)

        response = self.api.post(
            "/api/v1/chamados/",
            {
                "titulo": "Aberto pela equipe",
                "descricao": "Solicitado por telefone.",
                "categoria": "rede",
                "prioridade": "media",
                "solicitante": self.outro_usuario.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        chamado = Chamado.objects.get(titulo="Aberto pela equipe")
        self.assertEqual(chamado.usuario, self.outro_usuario)
        self.assertTrue(
            Notificacao.objects.filter(
                chamado=chamado, usuario=self.outro_usuario, mensagem__contains="pela equipe"
            ).exists()
        )

    def test_cliente_nao_pode_atualizar_chamado(self):
        # Cliente nao pode alterar status/prioridade como equipe de infra.
        chamado = self._chamado()
        self.api.force_authenticate(self.usuario)

        response = self.api.patch(
            f"/api/v1/chamados/{chamado.id}/",
            {"status": "concluido", "prioridade": "alta"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        chamado.refresh_from_db()
        self.assertEqual(chamado.status, "aberto")
        self.assertEqual(chamado.prioridade, "media")

    def test_notificacoes_sao_entregues_e_marcadas_como_lidas(self):
        chamado = self._chamado(status="andamento")
        notificacao = Notificacao.objects.create(
            usuario=self.usuario,
            chamado=chamado,
            tipo="status_chamado",
            mensagem="Seu chamado foi atualizado.",
        )
        self.api.force_authenticate(self.usuario)

        response = self.api.get("/api/v1/notificacoes/")
        self.assertEqual([n["id"] for n in response.json()["results"]], [notificacao.id])

        self.api.post("/api/v1/notificacoes/marcar-lidas/")
        notificacao.refresh_from_db()
        self.assertTrue(notificacao.lida)
        self.assertEqual(self.api.get("/api/v1/notificacoes/").json()["results"], [])


class CategoriasApiTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.cliente = User.objects.create_user(username="cliente", password="SenhaForte123!")
        self.staff = User.objects.create_user(
            username="tecnico", password="SenhaForte123!", is_staff=True
        )
        self.url = "/api/v1/categorias/"

    def test_categorias_iniciais_sao_criadas_pela_migracao(self):
        slugs = set(Categoria.objects.values_list("slug", flat=True))
        self.assertEqual(slugs, {"hardware", "software", "rede", "acesso", "outros"})

    def test_cliente_lista_somente_categorias_ativas(self):
        Categoria.objects.filter(slug="acesso").update(ativa=False)
        self.api.force_authenticate(self.cliente)

        # Mesmo pedindo ?todas=1, cliente nao ve categorias inativas.
        response = self.api.get(self.url, {"todas": "1"})

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("acesso", [c["slug"] for c in response.json()])

    def test_staff_ve_inativas_com_parametro_todas(self):
        Categoria.objects.filter(slug="acesso").update(ativa=False)
        self.api.force_authenticate(self.staff)

        response = self.api.get(self.url, {"todas": "1"})

        self.assertIn("acesso", [c["slug"] for c in response.json()])

    def test_cliente_nao_pode_criar_alterar_ou_excluir_categoria(self):
        self.api.force_authenticate(self.cliente)
        categoria = Categoria.objects.get(slug="rede")

        self.assertEqual(self.api.post(self.url, {"nome": "Impressora"}).status_code, 403)
        self.assertEqual(
            self.api.patch(f"{self.url}{categoria.id}/", {"ativa": False}).status_code, 403
        )
        self.assertEqual(self.api.delete(f"{self.url}{categoria.id}/").status_code, 403)

    def test_staff_cria_categoria_e_ela_fica_disponivel_no_chamado(self):
        self.api.force_authenticate(self.staff)

        response = self.api.post(self.url, {"nome": "Impressora"})

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["slug"], "impressora")

        self.api.force_authenticate(self.cliente)
        response_chamado = self.api.post(
            "/api/v1/chamados/",
            {"titulo": "Sem toner", "descricao": "Acabou.", "categoria": "impressora", "prioridade": "baixa"},
        )
        self.assertEqual(response_chamado.status_code, 201, response_chamado.content)
        self.assertEqual(response_chamado.json()["categoria_nome"], "Impressora")

    def test_nome_duplicado_e_rejeitado(self):
        self.api.force_authenticate(self.staff)

        response = self.api.post(self.url, {"nome": "  REDE "})

        self.assertEqual(response.status_code, 400)

    def test_renomear_mantem_slug_e_chamados_vinculados(self):
        categoria = Categoria.objects.get(slug="rede")
        chamado = Chamado.objects.create(
            titulo="Wi-Fi caiu", descricao="Sem sinal.", categoria=categoria,
            usuario=self.cliente, prioridade="alta",
        )
        self.api.force_authenticate(self.staff)

        response = self.api.patch(f"{self.url}{categoria.id}/", {"nome": "Redes"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["slug"], "rede")
        chamado.refresh_from_db()
        self.assertEqual(chamado.categoria.nome, "Redes")

    def test_categoria_inativa_nao_aceita_novos_chamados(self):
        Categoria.objects.filter(slug="hardware").update(ativa=False)
        self.api.force_authenticate(self.cliente)

        response = self.api.post(
            "/api/v1/chamados/",
            {"titulo": "PC", "descricao": "Nao liga.", "categoria": "hardware", "prioridade": "alta"},
        )

        self.assertEqual(response.status_code, 400)

    def test_excluir_categoria_em_uso_retorna_conflito(self):
        categoria = Categoria.objects.get(slug="software")
        Chamado.objects.create(
            titulo="Erro", descricao="Falha.", categoria=categoria,
            usuario=self.cliente, prioridade="media",
        )
        self.api.force_authenticate(self.staff)

        response = self.api.delete(f"{self.url}{categoria.id}/")

        self.assertEqual(response.status_code, 409)
        self.assertTrue(Categoria.objects.filter(pk=categoria.pk).exists())

    def test_excluir_categoria_sem_chamados(self):
        categoria = Categoria.objects.create(nome="Temporaria")
        self.api.force_authenticate(self.staff)

        response = self.api.delete(f"{self.url}{categoria.id}/")

        self.assertEqual(response.status_code, 204)
