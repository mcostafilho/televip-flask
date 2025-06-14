# 📱 TeleVIP - Sistema de Assinaturas para Grupos Telegram

Sistema completo para monetização de grupos no Telegram com pagamentos via Stripe.

## 🚀 Funcionalidades

- ✅ Gestão de múltiplos grupos
- ✅ Planos de assinatura personalizados
- ✅ Pagamentos via Stripe
- ✅ Bot Telegram automatizado
- ✅ Dashboard para criadores
- ✅ Painel administrativo
- ✅ Sistema de saques

## 📋 Pré-requisitos

- Python 3.8+
- PostgreSQL ou SQLite
- Conta Stripe
- Bot no Telegram

## 🛠️ Instalação

1. Clone o repositório
2. Crie um ambiente virtual: `python -m venv venv`
3. Ative o ambiente: `source venv/bin/activate` (Linux/Mac) ou `venv\Scripts\activate` (Windows)
4. Instale as dependências: `pip install -r requirements.txt`
5. Configure o `.env` baseado no `.env.example`
6. Execute: `python run.py`

## 📁 Estrutura do Projeto

```
televip-flask/
├── app/              # Aplicação Flask
├── bot/              # Bot Telegram
├── migrations/       # Migrações do banco
├── tests/           # Testes
└── config.py        # Configurações
```

## 📝 Licença

MIT License
