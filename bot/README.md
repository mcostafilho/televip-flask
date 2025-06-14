# 🤖 TeleVIP Bot

Bot do Telegram para gerenciamento automático de assinaturas de grupos VIP.

## 🚀 Funcionalidades

### Para Assinantes
- ✅ Escolher e pagar planos de assinatura
- ✅ Acesso automático aos grupos após pagamento
- ✅ Notificações de vencimento
- ✅ Renovação simplificada
- ✅ Verificação de status

### Para Criadores
- 📊 Estatísticas em tempo real
- 📢 Broadcast para assinantes
- 💰 Controle financeiro
- ⚙️ Configuração fácil do bot no grupo
- 🔔 Relatórios diários automáticos

## 📋 Pré-requisitos

1. **Bot no Telegram**
   - Crie um bot com [@BotFather](https://t.me/botfather)
   - Salve o token e username

2. **Python 3.8+**
   - Instale Python na sua máquina
   - Crie ambiente virtual

3. **Banco de Dados**
   - SQLite (desenvolvimento)
   - PostgreSQL (produção)

## 🛠️ Instalação

1. **Instalar dependências do bot:**
```bash
pip install -r bot/requirements.txt
```

2. **Configurar variáveis no `.env`:**
```env
# Bot
BOT_TOKEN=seu_token_aqui
BOT_USERNAME=seu_bot_username

# Banco de dados (mesmo do Flask)
DATABASE_URL=sqlite:///televip.db
```

3. **Executar setup:**
```bash
python setup_bot.py
```

## 🎮 Como Usar

### 1. Iniciar o Bot
```bash
python bot/main.py
```

### 2. Configurar um Grupo

1. Adicione o bot ao seu grupo
2. Promova o bot a administrador com permissões:
   - Adicionar membros
   - Remover membros
   - Gerenciar links de convite
3. Use o comando `/setup` dentro do grupo

### 3. Compartilhar Link de Assinatura

Após configurar, o bot fornecerá um link como:
```
https://t.me/seu_bot?start=g_ID_DO_GRUPO
```

Compartilhe este link com seus seguidores!

## 📱 Comandos do Bot

### Comandos Gerais
- `/start` - Iniciar conversa com o bot
- `/help` - Ver todos os comandos
- `/planos` - Ver planos ativos
- `/status` - Verificar status das assinaturas

### Comandos para Criadores
- `/setup` - Configurar bot no grupo (use dentro do grupo)
- `/stats` - Ver estatísticas
- `/broadcast [id_grupo] [mensagem]` - Enviar mensagem aos assinantes

## 🔄 Fluxo de Assinatura

1. **Usuário clica no link** → Bot mostra planos disponíveis
2. **Escolhe plano** → Bot gera PIX para pagamento
3. **Envia comprovante** → Bot verifica e adiciona ao grupo
4. **Próximo ao vencimento** → Bot notifica para renovar
5. **Assinatura expira** → Bot remove automaticamente

## 🔧 Configuração Avançada

### Notificações Automáticas
O bot envia automaticamente:
- Lembretes 3 dias antes do vencimento
- Confirmações de pagamento
- Avisos de remoção por expiração
- Relatórios diários para criadores (9h)

### Integração com Stripe (Opcional)
Para aceitar cartão de crédito:
1. Configure `STRIPE_SECRET_KEY` no `.env`
2. O bot oferecerá opção de pagamento via cartão

## 🐛 Troubleshooting

### Bot não responde
- Verifique se o token está correto
- Confirme que o bot está rodando
- Veja os logs no terminal

### Não consegue adicionar membros
- Bot precisa ser admin do grupo
- Verifique permissões do bot
- Grupo não pode estar com convites desativados

### Pagamentos não processam
- Verifique integração com Stripe
- Confirme que o banco está acessível
- Veja logs de erro

## 📊 Monitoramento

O bot registra todas as ações em logs:
- Pagamentos processados
- Membros adicionados/removidos
- Erros e exceções
- Estatísticas de uso

## 🚀 Deploy em Produção

### Usando Systemd (Linux)
1. Crie arquivo de serviço: `/etc/systemd/system/televip-bot.service`
2. Configure para iniciar automaticamente
3. Use PostgreSQL em vez de SQLite

### Usando Docker
```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY . .
RUN pip install -r bot/requirements.txt
CMD ["python", "bot/main.py"]
```

## 🤝 Suporte

Em caso de problemas:
1. Verifique os logs
2. Consulte a documentação
3. Abra uma issue no GitHub

---

💡 **Dica:** Mantenha o bot sempre atualizado para ter acesso às últimas funcionalidades e correções de segurança!