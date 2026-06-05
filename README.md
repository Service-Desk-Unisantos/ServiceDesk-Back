# Sistema de ServiceDesk para solucionar um problema real

## Configuração do Google OAuth 2.0

1. Copie `.env.example` para `.env`.
2. Preencha `GOOGLE_OAUTH_CLIENT_ID` e `GOOGLE_OAUTH_CLIENT_SECRET` com as credenciais criadas no Google Cloud Console.
3. Ajuste `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS` e `FRONTEND_GOOGLE_CALLBACK_URL` conforme o ambiente.
4. Instale as dependências com `pip install -r requirements.txt`.
5. Rode as migrações: `python ServiceDesk/manage.py migrate`.

No Google Cloud Console, cadastre esta URI de redirecionamento autorizado para desenvolvimento local:

`http://localhost:8000/accounts/google/login/callback/`

Quando as credenciais estiverem configuradas, a tela de login mostra o botão **Entrar com Google**.
