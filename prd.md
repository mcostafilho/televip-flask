# PRD — TeleVIP

## Product Requirements Document

**Versão:** 1.0  
**Data:** 09/02/2026  
**Produto:** TeleVIP — Sistema de Assinaturas para Grupos Telegram  
**Status:** Em desenvolvimento  

---

## 1. Visão Geral

### 1.1 O que é o TeleVIP?

O TeleVIP é uma plataforma SaaS que permite criadores de conteúdo monetizarem seus grupos no Telegram por meio de assinaturas pagas. A plataforma conecta criadores que possuem grupos exclusivos a assinantes que desejam acessá-los, automatizando todo o fluxo de cobrança, controle de acesso e gestão financeira.

### 1.2 Problema

Criadores de conteúdo no Telegram enfrentam dificuldades para monetizar seus grupos privados. Hoje, o processo é manual: o criador precisa cobrar individualmente, gerar links de convite, controlar quem pagou, remover quem não renovou e gerenciar finanças em planilhas. Isso é ineficiente, sujeito a erros e não escala.

### 1.3 Solução

O TeleVIP automatiza 100% desse fluxo por meio de um bot Telegram integrado a pagamentos via Stripe e um painel web de gestão. O criador cadastra seu grupo, define planos de preço, e o bot cuida de cobrar, liberar acesso e remover assinantes expirados automaticamente.

### 1.4 Proposta de Valor

- **Para criadores:** Monetize seus grupos sem esforço manual. Cadastre, defina preços e receba.
- **Para assinantes:** Processo de assinatura simples direto pelo Telegram com pagamento seguro.
- **Para a plataforma:** Receita por transação (R$ 0,99 + 9,99% por pagamento processado).

---

## 2. Público-Alvo

### 2.1 Criadores (Usuários Primários)

- Influenciadores e produtores de conteúdo no Telegram
- Educadores que oferecem cursos ou mentorias via grupos
- Comunidades de nicho (trading, fitness, tecnologia, jogos)
- Qualquer pessoa que administre grupos exclusivos no Telegram

### 2.2 Assinantes (Usuários Finais)

- Pessoas que desejam acessar conteúdo exclusivo em grupos do Telegram
- Interagem apenas com o bot Telegram, sem necessidade de cadastro web

---

## 3. Arquitetura do Sistema

### 3.1 Stack Tecnológico

| Componente | Tecnologia |
|---|---|
| Backend Web | Flask 3.0 (Python) |
| Banco de Dados | SQLite (dev) / PostgreSQL (prod) |
| ORM | SQLAlchemy 2.0 + Flask-Migrate (Alembic) |
| Autenticação Web | Flask-Login |
| Bot Telegram | python-telegram-bot 20.7 |
| Pagamentos | Stripe (checkout sessions) |
| Frontend | Templates Jinja2 + Bootstrap + Chart.js |

### 3.2 Componentes Principais

```
┌──────────────────────────────────────────────────────┐
│                    TeleVIP                           │
│                                                      │
│  ┌────────────┐   ┌──────────────┐   ┌───────────┐  │
│  │  Flask Web  │   │  Bot Telegram │   │  Stripe   │  │
│  │  Dashboard  │◄──┤  (async)     │──►│  Webhooks │  │
│  └──────┬─────┘   └──────┬───────┘   └─────┬─────┘  │
│         │                │                   │        │
│         └────────┬───────┘───────────────────┘        │
│                  ▼                                    │
│         ┌────────────────┐                            │
│         │   PostgreSQL   │                            │
│         │   (SQLAlchemy) │                            │
│         └────────────────┘                            │
└──────────────────────────────────────────────────────┘
```

### 3.3 Modelo de Dados

**Entidades principais:**

- **Creator** — Criador de conteúdo (usuário web). Campos: nome, email, username, senha, telegram_id, balance, total_earned, pix_key, status.
- **Group** — Grupo Telegram gerenciado. Campos: nome, descrição, telegram_id, invite_link, creator_id (FK), is_active, total_subscribers.
- **PricingPlan** — Plano de preço de um grupo. Campos: nome, duration_days, price, group_id (FK), stripe_price_id, is_active.
- **Subscription** — Assinatura de um usuário em um grupo. Campos: group_id (FK), plan_id (FK), telegram_user_id, status (active/expired/cancelled), start_date, end_date.
- **Transaction** — Registro financeiro de pagamento. Campos: subscription_id (FK), amount, fixed_fee, percentage_fee, total_fee, net_amount, status, payment_method, stripe_session_id.
- **Withdrawal** — Solicitação de saque do criador. Campos: creator_id (FK), amount, pix_key, status (pending/completed/rejected).

**Relacionamentos:**
```
Creator 1──N Group 1──N PricingPlan
                 │
                 └──N Subscription 1──N Transaction
                         │
Creator 1──N Withdrawal  └── PricingPlan (FK)
```

---

## 4. Funcionalidades

### 4.1 Painel Web do Criador

#### 4.1.1 Autenticação
- **Registro** com nome, email, username e senha (validação de força de senha no frontend)
- **Login** com email/senha + opção "lembrar-me"
- **Recuperação de senha** via token por email
- **Logout**

#### 4.1.2 Dashboard Principal
- Cards com métricas: saldo disponível, receita total, assinantes ativos, total de grupos
- Gráfico de receita dos últimos 7 dias (Chart.js)
- Lista de grupos com status e assinantes
- Transações recentes
- Ações rápidas: criar grupo, solicitar saque, ver analytics, editar perfil

#### 4.1.3 Gestão de Grupos
- **Criar grupo:** nome, descrição, telegram_id, link de convite, opção de pular validação do Telegram
- **Editar grupo:** alterar dados, ativar/desativar, gerenciar planos de preço
- **Ver assinantes:** lista paginada com username, plano, status, datas, valor pago
- **Exportar assinantes:** download em CSV
- **Estatísticas do grupo:** métricas detalhadas por grupo
- **Link do bot:** gerado automaticamente no formato `https://t.me/{bot}?start=g_{id}`
- **Limites:** máximo de 10 grupos por criador, máximo de 5 planos por grupo

#### 4.1.4 Planos de Preço
- Nome personalizado (ex: "Mensal", "Trimestral", "Anual")
- Duração em dias
- Preço em R$ (BRL)
- Ativar/desativar planos individualmente
- Integração com Stripe Price ID

#### 4.1.5 Transações
- Listagem paginada com filtros por status e grupo
- Status: pending, completed, failed, refunded
- Detalhamento de taxas por transação

#### 4.1.6 Analytics
- Período configurável (7d, 30d, 90d)
- Receita por dia (gráfico de linha)
- Assinantes por dia (gráfico de linha)
- Receita por grupo (gráfico de pizza)
- Receita por plano (gráfico de pizza)
- KPIs: receita total, total de transações, ticket médio, assinantes ativos, novos assinantes

#### 4.1.7 Perfil
- Editar nome, email, chave PIX
- Visualizar histórico de saques
- Informações da conta

#### 4.1.8 Saques
- Solicitar saque do saldo disponível
- Valor mínimo: R$ 50,00
- Método: PIX (chave cadastrada no perfil)
- Prazo: até 3 dias úteis
- Histórico de saques com status

### 4.2 Painel Administrativo

- Acesso restrito por decorator `@admin_required`
- Dashboard com estatísticas globais: total de criadores, grupos, assinaturas ativas, saques pendentes
- Lista de todos os criadores com métricas individuais
- Detalhes do criador: grupos, assinantes, receita, transações recentes
- Processamento de saques pendentes (aprovar/rejeitar)
- Login como criador (impersonação para suporte)
- Envio de mensagens para criadores

### 4.3 Bot Telegram

#### 4.3.1 Comandos
| Comando | Descrição |
|---|---|
| `/start` | Dashboard do usuário com assinaturas ativas |
| `/start g_{id}` | Inicia fluxo de assinatura para um grupo específico |
| `/start success_{id}` | Retorno de pagamento bem-sucedido |
| `/start cancel` | Retorno de pagamento cancelado |
| `/descobrir` | Descobrir grupos disponíveis na plataforma |
| `/subscriptions` | Listar assinaturas ativas |
| `/setup` | (Em grupo) Mostra status do bot como admin |

#### 4.3.2 Fluxo de Assinatura
1. Usuário clica em link `t.me/bot?start=g_{id}`
2. Bot exibe informações do grupo e planos disponíveis
3. Usuário seleciona plano → bot mostra resumo com valores e taxas
4. Usuário escolhe método de pagamento (Cartão via Stripe ou PIX)
5. Bot gera link de checkout do Stripe
6. Após pagamento → webhook do Stripe notifica o sistema
7. Sistema ativa assinatura e tenta adicionar o usuário ao grupo
8. Se não conseguir adicionar diretamente, gera link de convite único (válido 7 dias)

#### 4.3.3 Descoberta de Grupos
- Grupos populares (ordenados por assinantes)
- Grupos novos (ordenados por data de criação)
- Grupos mais baratos (ordenados por menor preço)
- Grupos premium (filtro por preço alto)
- Navegação por categorias (Educação, Fitness, Tecnologia, Investimentos, Entretenimento, Outros)

#### 4.3.4 Callbacks do Bot
| Callback | Ação |
|---|---|
| `plan_{groupId}_{planId}` | Selecionar plano de assinatura |
| `pay_stripe` / `pay_pix` | Escolher método de pagamento |
| `discover` | Abrir catálogo de grupos |
| `categories` | Ver categorias |
| `premium_groups` | Filtrar grupos premium |
| `new_groups` | Ver grupos recentes |
| `cheapest_groups` | Ver grupos mais baratos |
| `check_payment_status` | Verificar status do pagamento |
| `back_to_start` | Voltar ao menu principal |
| `my_subscriptions` | Ver assinaturas ativas |

### 4.4 Sistema de Pagamentos

#### 4.4.1 Integração Stripe
- Checkout Sessions para pagamentos únicos
- Moeda: BRL (Real Brasileiro)
- Métodos: cartão de crédito/débito
- Webhooks para notificação de eventos:
  - `checkout.session.completed` — pagamento aprovado
  - `payment_intent.succeeded` — confirmação de pagamento
  - `payment_intent.payment_failed` — falha no pagamento
  - `charge.dispute.created` — disputa/chargeback
- Verificação de assinatura via `stripe.Webhook.construct_event()`

#### 4.4.2 Modelo de Taxas
| Componente | Valor |
|---|---|
| Taxa fixa | R$ 0,99 por transação |
| Taxa percentual | 9,99% do valor bruto |
| Valor mínimo para saque | R$ 50,00 |
| Máximo de grupos por criador | 10 |
| Máximo de planos por grupo | 5 |

**Exemplo de cálculo:**
- Venda de R$ 100,00
- Taxa fixa: R$ 0,99
- Taxa percentual: R$ 9,99 (9,99% de R$ 100)
- Taxa total: R$ 10,98
- Líquido para criador: R$ 89,02
- Taxa efetiva: 10,98%

#### 4.4.3 Fluxo Financeiro
```
Assinante paga R$ 100,00
     │
     ▼
Stripe processa pagamento
     │
     ▼
Webhook notifica TeleVIP
     │
     ▼
TeleVIP calcula taxas (R$ 10,98)
     │
     ▼
Credita R$ 89,02 no saldo do Criador
     │
     ▼
Criador solicita saque (mín R$ 50)
     │
     ▼
Admin processa via PIX (até 3 dias úteis)
```

---

## 5. Rotas da Aplicação

### 5.1 Rotas Públicas
| Rota | Método | Descrição |
|---|---|---|
| `/` | GET | Landing page |
| `/login` | GET, POST | Login |
| `/register` | GET, POST | Registro |
| `/forgot-password` | GET, POST | Recuperação de senha |
| `/reset-password/<token>` | GET, POST | Redefinir senha |

### 5.2 Rotas do Dashboard (autenticado)
| Rota | Método | Descrição |
|---|---|---|
| `/dashboard` | GET | Dashboard principal |
| `/dashboard/transactions` | GET | Listagem de transações |
| `/dashboard/withdrawals` | GET | Histórico de saques |
| `/dashboard/withdraw` | POST | Solicitar saque |
| `/dashboard/profile` | GET | Perfil do criador |
| `/dashboard/profile/update` | POST | Atualizar perfil |
| `/dashboard/analytics` | GET | Analytics detalhado |

### 5.3 Rotas de Grupos (autenticado)
| Rota | Método | Descrição |
|---|---|---|
| `/groups` | GET | Listar grupos |
| `/groups/create` | GET, POST | Criar grupo |
| `/groups/<id>/edit` | GET, POST | Editar grupo |
| `/groups/<id>/subscribers` | GET | Ver assinantes |
| `/groups/<id>/export-subscribers` | GET | Exportar CSV |
| `/groups/<id>/stats` | GET | Estatísticas |

### 5.4 Rotas Admin (admin_required)
| Rota | Método | Descrição |
|---|---|---|
| `/admin` | GET | Painel admin |
| `/admin/withdrawal/<id>/process` | POST | Processar saque |
| `/admin/creator/<id>/details` | GET | Detalhes do criador |
| `/admin/creator/<id>/message` | POST | Enviar mensagem |
| `/admin/login-as/<id>` | GET | Impersonar criador |

### 5.5 Webhooks
| Rota | Método | Descrição |
|---|---|---|
| `/webhooks/stripe` | POST | Webhook do Stripe |

### 5.6 API
| Rota | Descrição |
|---|---|
| `/api/*` | Reservado para API do bot (não implementado) |

---

## 6. Configuração e Deploy

### 6.1 Variáveis de Ambiente
| Variável | Descrição | Obrigatória |
|---|---|---|
| `SECRET_KEY` | Chave secreta do Flask | Sim |
| `DATABASE_URL` | URL de conexão do banco | Sim |
| `BOT_TOKEN` | Token do bot Telegram | Sim |
| `TELEGRAM_BOT_USERNAME` | Username do bot | Sim |
| `STRIPE_SECRET_KEY` | Chave secreta do Stripe | Sim |
| `STRIPE_WEBHOOK_SECRET` | Secret do webhook Stripe | Sim |
| `STRIPE_PUBLIC_KEY` | Chave pública do Stripe | Não |
| `BASE_URL` | URL base da aplicação | Sim (prod) |
| `FLASK_ENV` | Ambiente (development/production) | Não |

### 6.2 Pré-requisitos
- Python 3.8+
- PostgreSQL (produção) ou SQLite (desenvolvimento)
- Conta Stripe com chaves de API
- Bot Telegram criado via @BotFather
- Servidor com HTTPS (para webhooks)

### 6.3 Dependências Principais
- Flask 3.0, Flask-SQLAlchemy, Flask-Login, Flask-Migrate, Flask-Cors
- SQLAlchemy 2.0.36
- stripe 7.8.0
- python-telegram-bot 20.7
- bcrypt, gunicorn, python-dotenv
- qrcode, pillow

---

## 7. Segurança

### 7.1 Implementado
- Senhas hasheadas com Werkzeug (PBKDF2)
- CSRF protection via WTF_CSRF_ENABLED
- Verificação de assinatura nos webhooks do Stripe
- Decorator `@admin_required` para rotas administrativas
- Validação de entrada em formulários (email regex, username regex, senha mínima)
- Sanitização de nomes de arquivo para uploads
- Session com expiração (24h)
- CORS configurado

### 7.2 Pendente / Recomendado
- Rate limiting em rotas de autenticação
- Validação de redirect no parâmetro `next` (open redirect)
- Forçar SECRET_KEY em produção (remover fallback)
- HMAC-SHA256 consistente em todas as verificações de webhook
- Migrar campos monetários de Float para Numeric/Decimal
- Implementar HTTPS obrigatório
- Headers de segurança (CSP, HSTS, X-Frame-Options)

---

## 8. Métricas e KPIs

### 8.1 Métricas de Negócio
- GMV (volume total de transações)
- Receita da plataforma (taxas cobradas)
- Número de criadores ativos
- Número de assinantes ativos
- Ticket médio por transação
- Taxa de conversão (visitante → assinante)
- Churn rate (taxa de não-renovação)

### 8.2 Métricas Técnicas
- Uptime do bot e da aplicação web
- Tempo de resposta do bot
- Taxa de sucesso de pagamentos
- Tempo entre pagamento e liberação de acesso

---

## 9. Roadmap

### 9.1 MVP Atual (v1.0)
- [x] Cadastro e login de criadores
- [x] CRUD de grupos e planos
- [x] Bot Telegram com fluxo de assinatura
- [x] Pagamento via Stripe (cartão)
- [x] Dashboard com métricas e gráficos
- [x] Painel administrativo
- [x] Descoberta de grupos no bot
- [x] Exportação de assinantes (CSV)
- [x] Sistema de saques via PIX

### 9.2 Próximas Iterações (v1.x)
- [ ] Pagamento via PIX nativo (integração direta)
- [ ] Renovação automática de assinaturas
- [ ] Notificações de expiração (3 dias antes, 1 dia antes)
- [ ] Remoção automática de assinantes expirados
- [ ] Cupons de desconto
- [ ] Período de teste gratuito (trial)
- [ ] API REST pública para integrações

### 9.3 Futuro (v2.0)
- [ ] Marketplace público de grupos
- [ ] Sistema de afiliados
- [ ] Dashboard mobile (app ou PWA)
- [ ] Múltiplos gateways de pagamento (Mercado Pago, PagSeguro)
- [ ] Webhooks para criadores (notificações de novas assinaturas)
- [ ] Integrações com outras plataformas (Discord, WhatsApp)
- [ ] Analytics avançado com cohort analysis e previsão de churn

---

## 10. Glossário

| Termo | Definição |
|---|---|
| **Criador** | Usuário que gerencia grupos e recebe pagamentos |
| **Assinante** | Usuário do Telegram que paga para acessar um grupo |
| **Grupo** | Canal ou grupo Telegram gerenciado via TeleVIP |
| **Plano** | Opção de assinatura com preço e duração definidos |
| **Transação** | Registro de pagamento realizado por um assinante |
| **Saque** | Solicitação do criador para transferir saldo para PIX |
| **Taxa fixa** | R$ 0,99 cobrados por transação |
| **Taxa percentual** | 9,99% do valor bruto cobrados por transação |
| **Net amount** | Valor líquido creditado ao criador após taxas |
| **Checkout Session** | Sessão de pagamento do Stripe para processar cobranças |
| **Deep link** | Link do Telegram no formato `t.me/bot?start=g_{id}` que inicia fluxo de assinatura |