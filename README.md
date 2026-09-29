# MONEY TIPS — versão segura

## O que foi corrigido
- A chave da API de futebol não fica mais no HTML.
- O navegador chama `/api/football/...` e o Flask consulta o football-data.org no servidor.
- Login e cadastro usam SQLite + senha com hash, em vez de guardar senhas no `localStorage`.
- Sessão usa cookie HTTPOnly/SameSite.
- Admin é definido no servidor pelas variáveis `ADMIN_EMAIL` e `ADMIN_PASSWORD`.
- O botão “Entrar como Admin” não concede acesso: ele apenas leva ao formulário de login.
- Alterações de plano/status passam por rotas protegidas no servidor.
- O JavaScript foi validado com `node --check`.

## Instalação

1. Instale Python 3.10+.
2. No terminal, entre nesta pasta.
3. Instale dependências:
   `pip install -r requirements.txt`
4. Defina as variáveis de `.env.example` no ambiente.
5. Inicie:
   `python app.py`
6. Abra `http://127.0.0.1:5000`.

A chave do football-data.org deve ser colocada em `FOOTBALL_DATA_API_KEY` no servidor.

## Produção
Use HTTPS e defina `COOKIE_SECURE=1`. Não coloque `.env`, `moneytips.db` ou segredos dentro do HTML público. Para publicação, use um servidor WSGI (por exemplo Gunicorn) atrás de HTTPS/reverse proxy.
