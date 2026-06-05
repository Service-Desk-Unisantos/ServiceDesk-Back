# servicedesk-backend

Backend do sistema ServiceDesk — servidor web, regras de negócio, banco de dados e API REST.

---

## Tecnologias

| Camada | Tecnologia |
|--------|-----------|
| Framework web | [Django 5](https://www.djangoproject.com/) |
| API REST | [Django REST Framework](https://www.django-rest-framework.org/) + [drf-nested-routers](https://github.com/alanjds/drf-nested-routers) |
| Autenticação JWT | [SimpleJWT](https://django-rest-framework-simplejwt.readthedocs.io/) |
| Login social | [django-allauth](https://docs.allauth.org/) (Google OAuth 2.0) |
| Banco de dados | SQLite 3 (desenvolvimento) |
| Notificações em tempo real | Servidor TCP socket customizado (porta 8765) + polling HTTP a cada 5s como fallback |
| CORS | [django-cors-headers](https://github.com/adamchainz/django-cors-headers) |
| Monitoramento de processo | [psutil](https://psutil.readthedocs.io/) |

---

## Arquitetura

```
ServiceDesk/
├── ConfigDjango/          # Configurações do projeto Django
│   ├── settings.py
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
├── chamados/              # App principal
│   ├── models.py          # Chamado, Comentario, Notificacao
│   ├── views.py           # Views HTML (interface web)
│   ├── forms.py
│   ├── backends.py        # Autenticação por username ou e-mail
│   ├── urls.py
│   └── api/               # Endpoints REST
│       ├── views.py
│       ├── serializers.py
│       ├── urls.py
│       └── permissions.py
├── server_socket.py       # Servidor TCP de notificações em tempo real
└── manage.py
finops.py                  # Monitoramento de custos de CPU/RAM
```

### Modelos principais

**Chamado** — unidade central do sistema  
Campos: `titulo`, `descricao`, `categoria` (Hardware / Software / Rede / Acesso / Outros), `status` (Aberto / Em andamento / Concluído), `prioridade` (Baixa / Média / Alta), `usuario`, `data_criacao`

**Comentario** — histórico de comunicação entre cliente e equipe  
Campos: `chamado`, `usuario`, `texto`, `data`

**Notificacao** — notificações persistidas para entrega por polling  
Campos: `usuario`, `chamado`, `tipo`, `mensagem`, `lida`, `criada_em`

---

## API REST

Base URL: `/api/`  
Autenticação: Bearer Token (JWT)

| Método | Endpoint | Descrição | Permissão |
|--------|----------|-----------|-----------|
| POST | `/api/auth/login/` | Autenticar e receber tokens JWT | Público |
| POST | `/api/auth/cadastro/` | Criar conta e receber tokens JWT | Público |
| POST | `/api/auth/token/refresh/` | Renovar access token | Público |
| POST | `/api/auth/token/blacklist/` | Invalidar refresh token (logout) | Autenticado |
| GET | `/api/chamados/` | Listar chamados (cliente vê os próprios, staff vê todos) | Autenticado |
| POST | `/api/chamados/` | Abrir novo chamado | Autenticado |
| GET | `/api/chamados/{id}/` | Detalhar chamado | Autenticado |
| PATCH | `/api/chamados/{id}/` | Atualizar status/prioridade | Staff |
| GET | `/api/chamados/{id}/comentarios/` | Listar comentários do chamado | Autenticado |
| POST | `/api/chamados/{id}/comentarios/` | Adicionar comentário | Dono ou Staff |
| GET | `/api/notificacoes/` | Listar notificações não lidas | Autenticado |
| POST | `/api/notificacoes/marcar-lidas/` | Marcar todas como lidas | Autenticado |

---

## Configuração e instalação

**Pré-requisitos:** Python 3.11+

```bash
# 1. Clonar o repositório
git clone <url-do-repositorio>
cd ServiceDesk

# 2. Criar e ativar ambiente virtual
python -m venv venv
source venv/bin/activate        # Linux/macOS
venv\Scripts\activate           # Windows

# 3. Instalar dependências
pip install -r requirements.txt

# 4. Configurar variáveis de ambiente
cp .env.example .env
# Preencher .env com as chaves necessárias (ver seção abaixo)

# 5. Aplicar migrações
python ServiceDesk/manage.py migrate

# 6. Criar superusuário (equipe técnica)
python ServiceDesk/manage.py createsuperuser

# 7. Iniciar servidor
python ServiceDesk/manage.py runserver
```

Para habilitar notificações em tempo real, iniciar o servidor TCP em outro terminal:

```bash
python ServiceDesk/server_socket.py
```

---

## Variáveis de ambiente

Arquivo `.env` na raiz do projeto:

```env
DJANGO_SECRET_KEY=sua-chave-secreta
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

# Google OAuth 2.0 (opcional — o botão "Entrar com Google" só aparece quando configurado)
GOOGLE_OAUTH_CLIENT_ID=
GOOGLE_OAUTH_CLIENT_SECRET=
```

As credenciais Google OAuth são obtidas no [Google Cloud Console](https://console.cloud.google.com/).

---

## Módulo FinOps

O arquivo `finops.py` na raiz é um script independente que simula carga de CPU e RAM durante 45 segundos e gera dois relatórios:

- `relatorio_custos.csv` — métricas segundo a segundo (CPU%, RAM MB, custo parcial, custo acumulado)
- `analise_finops.pdf` — gráfico de custo acumulado + diagnóstico técnico, gerado sem bibliotecas externas

```bash
python finops.py
```

---

## Perfis de acesso

| Perfil | Criação | Capacidades |
|--------|---------|-------------|
| Cliente | Cadastro público ou login com Google | Abrir chamados, acompanhar status, enviar mensagens |
| Staff / Admin | `createsuperuser` ou painel Django Admin | Gerenciar todos os chamados, atualizar status e prioridade, responder |
