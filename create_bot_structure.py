#!/usr/bin/env python3
"""
Script para criar a estrutura completa do Bot TeleVIP
Execução: python create_bot_structure.py
"""

import os
import shutil

def create_directory(path):
    """Cria um diretório se não existir"""
    os.makedirs(path, exist_ok=True)
    print(f"✅ Criado diretório: {path}")

def create_file(path, content=""):
    """Cria um arquivo com conteúdo"""
    # Criar diretório pai se não existir
    os.makedirs(os.path.dirname(path), exist_ok=True)
    
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"✅ Criado arquivo: {path}")

def main():
    """Função principal"""
    print("🚀 Criando estrutura do Bot TeleVIP...\n")
    
    # Verificar se já existe pasta bot
    if os.path.exists('bot'):
        response = input("⚠️  A pasta 'bot' já existe. Deseja removê-la? (s/n): ")
        if response.lower() == 's':
            shutil.rmtree('bot')
            print("🗑️  Pasta 'bot' removida.\n")
        else:
            print("❌ Operação cancelada.")
            return
    
    # Criar estrutura de diretórios
    directories = [
        "bot",
        "bot/handlers",
        "bot/keyboards",
        "bot/utils",
        "bot/jobs",
    ]
    
    for directory in directories:
        create_directory(directory)
    
    print("\n📄 Criando arquivos...\n")
    
    # bot/__init__.py
    create_file("bot/__init__.py", '''"""
Bot TeleVIP - Sistema Multi-Criador
"""
__version__ = "2.0.0"
''')
    
    # bot/main.py
    create_file("bot/main.py", '''#!/usr/bin/env python3
"""
Bot principal do TeleVIP - Sistema Multi-Criador
"""
import os
import sys
import asyncio
import logging
from datetime import datetime
from dotenv import load_dotenv

# Adicionar o diretório raiz ao path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, filters, ContextTypes
)

# Importar handlers
from bot.handlers.start import start_command, help_command
from bot.handlers.payment import handle_plan_selection, handle_payment_callback
from bot.handlers.subscription import (
    status_command, planos_command, handle_renewal
)
from bot.handlers.admin import (
    setup_command, stats_command, broadcast_command
)
from bot.handlers.discovery import descobrir_command, handle_discover_callback
from bot.jobs.scheduled_tasks import setup_jobs

# Carregar variáveis de ambiente
load_dotenv()

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def main():
    """Função principal"""
    # Token do bot
    token = os.getenv('BOT_TOKEN')
    if not token:
        logger.error("BOT_TOKEN não configurado!")
        sys.exit(1)
    
    # Criar aplicação
    application = Application.builder().token(token).build()
    
    # Registrar comandos para usuários
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("planos", planos_command))
    application.add_handler(CommandHandler("descobrir", descobrir_command))
    
    # Registrar comandos admin
    application.add_handler(CommandHandler("setup", setup_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    
    # Registrar callbacks
    application.add_handler(CallbackQueryHandler(
        handle_plan_selection, pattern="^plan_"
    ))
    application.add_handler(CallbackQueryHandler(
        handle_payment_callback, pattern="^pay_"
    ))
    application.add_handler(CallbackQueryHandler(
        handle_renewal, pattern="^renew_"
    ))
    application.add_handler(CallbackQueryHandler(
        handle_discover_callback, pattern="^discover$"
    ))
    
    # Configurar jobs agendados
    setup_jobs(application)
    
    # Callback de inicialização
    application.post_init = post_init
    
    # Iniciar bot
    logger.info("🤖 Bot TeleVIP iniciando...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

async def post_init(application: Application) -> None:
    """Executado após a inicialização do bot"""
    bot_info = await application.bot.get_me()
    logger.info(f"✅ Bot @{bot_info.username} iniciado com sucesso!")
    
    # Definir comandos no menu do Telegram
    await application.bot.set_my_commands([
        ("start", "Ver suas assinaturas ou assinar novo grupo"),
        ("status", "Status detalhado de todas assinaturas"),
        ("planos", "Ver todos seus planos ativos"),
        ("descobrir", "Descobrir novos grupos"),
        ("help", "Obter ajuda"),
        ("setup", "Configurar bot no grupo (admin)"),
        ("stats", "Ver estatísticas (admin)")
    ])
    
    logger.info("📱 Comandos registrados no menu do Telegram")

if __name__ == '__main__':
    main()
''')
    
    # bot/handlers/__init__.py
    create_file("bot/handlers/__init__.py", '''"""
Handlers do Bot TeleVIP
"""
''')
    
    # bot/handlers/start.py
    create_file("bot/handlers/start.py", '''"""
Handler do comando /start com suporte multi-criador
"""
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from bot.utils.database import get_db_session
from app.models import Group, Creator, PricingPlan, Subscription

logger = logging.getLogger(__name__)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler do comando /start
    - Sem parâmetros: mostra dashboard do usuário
    - Com g_XXXXX: inicia fluxo de assinatura
    """
    user = update.effective_user
    args = context.args
    
    # Sem argumentos - mostrar dashboard
    if not args:
        await show_user_dashboard(update, context)
        return
    
    # Com argumento de grupo
    if args[0].startswith('g_'):
        group_id = args[0][2:]
        await start_subscription_flow(update, context, group_id)
        return
    
    # Argumento inválido
    await update.message.reply_text(
        "❌ Link inválido. Use o link fornecido pelo criador."
    )

async def show_user_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostrar dashboard com assinaturas do usuário"""
    # TODO: Implementar dashboard completo
    await update.message.reply_text(
        "🚧 Dashboard em construção...\\n\\n"
        "Use /descobrir para ver grupos disponíveis!",
        parse_mode=ParseMode.MARKDOWN
    )

async def start_subscription_flow(update: Update, context: ContextTypes.DEFAULT_TYPE, group_id: str):
    """Iniciar fluxo de assinatura para um grupo específico"""
    # TODO: Implementar fluxo de assinatura
    await update.message.reply_text(
        f"🚧 Iniciando assinatura para grupo {group_id}...",
        parse_mode=ParseMode.MARKDOWN
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando de ajuda"""
    help_text = """
📋 **Comandos Disponíveis:**

**Para Usuários:**
/start - Ver suas assinaturas ou iniciar nova
/status - Status detalhado das assinaturas
/planos - Listar todos seus planos ativos
/descobrir - Descobrir novos grupos

**Para Criadores (Admin):**
/setup - Configurar bot no grupo
/stats - Ver estatísticas
/broadcast - Enviar mensagem em massa

💡 **Dicas:**
• Ative notificações para avisos de renovação
• Renove com antecedência para ganhar desconto
• Use /descobrir para encontrar novos grupos

📞 **Suporte:**
Em caso de problemas, contate o criador do grupo.
"""
    
    await update.message.reply_text(
        help_text,
        parse_mode=ParseMode.MARKDOWN
    )
''')
    
    # bot/handlers/payment.py
    create_file("bot/handlers/payment.py", '''"""
Handler para processamento de pagamentos multi-criador
"""
import os
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from bot.utils.database import get_db_session
from bot.utils.stripe_integration import create_checkout_session
from app.models import Group, PricingPlan, Subscription, Transaction, Creator

logger = logging.getLogger(__name__)

async def handle_plan_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processar seleção de plano"""
    query = update.callback_query
    await query.answer()
    
    # TODO: Implementar seleção de plano
    await query.edit_message_text("🚧 Processamento de pagamento em construção...")

async def handle_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processar callback de pagamento"""
    query = update.callback_query
    await query.answer()
    
    # TODO: Implementar callback de pagamento
    await query.edit_message_text("🚧 Callback de pagamento em construção...")
''')
    
    # bot/handlers/subscription.py
    create_file("bot/handlers/subscription.py", '''"""
Handler para gerenciamento de assinaturas
"""
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from bot.utils.database import get_db_session
from app.models import Subscription, Group, Creator

logger = logging.getLogger(__name__)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostrar status detalhado de todas as assinaturas"""
    # TODO: Implementar status completo
    await update.message.reply_text(
        "🚧 Status em construção...\\n\\n"
        "Use /descobrir para ver grupos disponíveis!",
        parse_mode=ParseMode.MARKDOWN
    )

async def planos_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Listar todos os planos disponíveis"""
    # TODO: Implementar listagem de planos
    await update.message.reply_text(
        "🚧 Listagem de planos em construção...",
        parse_mode=ParseMode.MARKDOWN
    )

async def handle_renewal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processar renovação de assinatura"""
    query = update.callback_query
    await query.answer()
    
    # TODO: Implementar renovação
    await query.edit_message_text("🚧 Renovação em construção...")
''')
    
    # bot/handlers/admin.py
    create_file("bot/handlers/admin.py", '''"""
Comandos administrativos para criadores
"""
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from bot.utils.database import get_db_session
from app.models import Group, Creator, Subscription, Transaction

logger = logging.getLogger(__name__)

async def setup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Configurar bot no grupo"""
    chat = update.effective_chat
    user = update.effective_user
    
    # Verificar se é um grupo
    if chat.type == 'private':
        await update.message.reply_text(
            "❌ Este comando deve ser usado dentro do grupo!\\n\\n"
            "1. Adicione o bot ao grupo\\n"
            "2. Promova o bot a administrador\\n"
            "3. Use /setup dentro do grupo"
        )
        return
    
    # TODO: Implementar setup completo
    await update.message.reply_text(
        "🚧 Setup em construção...\\n\\n"
        f"ID do grupo: `{chat.id}`",
        parse_mode=ParseMode.MARKDOWN
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostrar estatísticas do grupo"""
    # TODO: Implementar estatísticas
    await update.message.reply_text(
        "🚧 Estatísticas em construção...",
        parse_mode=ParseMode.MARKDOWN
    )

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enviar mensagem para todos os assinantes"""
    # TODO: Implementar broadcast
    await update.message.reply_text(
        "🚧 Broadcast em construção...",
        parse_mode=ParseMode.MARKDOWN
    )
''')
    
    # bot/handlers/discovery.py
    create_file("bot/handlers/discovery.py", '''"""
Sistema de descoberta de grupos
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from sqlalchemy import func

from bot.utils.database import get_db_session
from app.models import Group, Subscription, PricingPlan

logger = logging.getLogger(__name__)

async def descobrir_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /descobrir - mostrar grupos populares"""
    await show_popular_groups(update, context)

async def show_popular_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostrar grupos mais populares"""
    # TODO: Implementar descoberta completa
    text = """
🔥 **Descobrir Grupos**

🚧 Sistema de descoberta em construção...

Em breve você poderá:
• Ver grupos populares
• Filtrar por categoria
• Ver avaliações
• Comparar preços

Volte em breve! 🚀
"""
    
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN
    )

async def handle_discover_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para callback de descoberta"""
    query = update.callback_query
    await query.answer()
    
    # Simular comando /descobrir
    update.message = query.message
    await show_popular_groups(update, context)
''')
    
    # bot/keyboards/__init__.py
    create_file("bot/keyboards/__init__.py", '''"""
Teclados do Bot TeleVIP
"""
''')
    
    # bot/keyboards/menus.py
    create_file("bot/keyboards/menus.py", '''"""
Teclados inline para o bot
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def get_main_menu() -> InlineKeyboardMarkup:
    """Menu principal do bot"""
    keyboard = [
        [
            InlineKeyboardButton("📊 Minhas Assinaturas", callback_data="my_subscriptions"),
            InlineKeyboardButton("🔍 Descobrir", callback_data="discover")
        ],
        [
            InlineKeyboardButton("💰 Histórico", callback_data="payment_history"),
            InlineKeyboardButton("⚙️ Configurações", callback_data="settings")
        ],
        [
            InlineKeyboardButton("❓ Ajuda", callback_data="help")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_plans_menu(plans: list, group_id: int) -> InlineKeyboardMarkup:
    """Menu de seleção de planos"""
    keyboard = []
    
    for plan in plans:
        keyboard.append([
            InlineKeyboardButton(
                f"{plan.name} - R$ {plan.price:.2f}",
                callback_data=f"plan_{group_id}_{plan.id}"
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton("❌ Cancelar", callback_data="cancel")
    ])
    
    return InlineKeyboardMarkup(keyboard)

def get_payment_keyboard() -> InlineKeyboardMarkup:
    """Teclado para opções de pagamento"""
    keyboard = [
        [
            InlineKeyboardButton("💳 Cartão (Stripe)", callback_data="pay_stripe")
        ],
        [
            InlineKeyboardButton("💰 PIX", callback_data="pay_pix")
        ],
        [
            InlineKeyboardButton("❌ Cancelar", callback_data="cancel_payment")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_admin_menu() -> InlineKeyboardMarkup:
    """Menu administrativo para criadores"""
    keyboard = [
        [
            InlineKeyboardButton("📊 Estatísticas", callback_data="admin_stats"),
            InlineKeyboardButton("👥 Assinantes", callback_data="admin_subscribers")
        ],
        [
            InlineKeyboardButton("💰 Financeiro", callback_data="admin_finance"),
            InlineKeyboardButton("⚙️ Configurações", callback_data="admin_settings")
        ],
        [
            InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)
''')
    
    # bot/utils/__init__.py
    create_file("bot/utils/__init__.py", '''"""
Utilitários do Bot TeleVIP
"""
''')
    
    # bot/utils/database.py
    create_file("bot/utils/database.py", '''"""
Utilitários para conexão com banco de dados
"""
import os
import sys
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv

# Adicionar o diretório raiz ao path para importar os models
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

load_dotenv()

# Configurar engine - usar o mesmo banco do Flask
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///instance/televip.db')

# Se for SQLite relativo, ajustar o caminho
if DATABASE_URL.startswith('sqlite:///') and not DATABASE_URL.startswith('sqlite:////'):
    db_path = DATABASE_URL.replace('sqlite:///', '')
    if not os.path.isabs(db_path):
        root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        full_path = os.path.join(root_dir, db_path)
        DATABASE_URL = f'sqlite:///{full_path}'

print(f"Bot usando banco de dados: {DATABASE_URL}")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@contextmanager
def get_db_session() -> Session:
    """Context manager para sessão do banco de dados"""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
''')
    
    # bot/utils/stripe_integration.py
    create_file("bot/utils/stripe_integration.py", '''"""
Integração com Stripe para o bot
"""
import os
import stripe
from typing import Dict

stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

async def create_checkout_session(
    amount: float,
    group_name: str,
    plan_name: str,
    user_id: str,
    success_url: str,
    cancel_url: str
) -> Dict:
    """Criar sessão de checkout no Stripe"""
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'brl',
                    'product_data': {
                        'name': f'{group_name} - {plan_name}',
                        'description': f'Assinatura do grupo {group_name}'
                    },
                    'unit_amount': int(amount * 100),  # Stripe usa centavos
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                'user_id': user_id,
                'group_name': group_name,
                'plan_name': plan_name
            }
        )
        
        return {
            'success': True,
            'session_id': session.id,
            'url': session.url
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

async def verify_payment(session_id: str) -> bool:
    """Verificar se pagamento foi completado"""
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        return session.payment_status == 'paid'
    except:
        return False
''')
    
    # bot/utils/notifications.py
    create_file("bot/utils/notifications.py", '''"""
Sistema de notificações do bot
"""
import logging
import asyncio
from datetime import datetime, timedelta
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

from bot.utils.database import get_db_session
from app.models import Subscription

logger = logging.getLogger(__name__)

class NotificationScheduler:
    """Agendador de notificações"""
    
    def __init__(self, bot: Bot):
        self.bot = bot
        self.running = False
        self.tasks = []
    
    async def start(self):
        """Iniciar scheduler"""
        self.running = True
        logger.info("📅 NotificationScheduler iniciado")
        
        # Agendar tarefas
        self.tasks.append(
            asyncio.create_task(self.check_expired_loop())
        )
        self.tasks.append(
            asyncio.create_task(self.send_reminders_loop())
        )
    
    async def stop(self):
        """Parar scheduler"""
        self.running = False
        for task in self.tasks:
            task.cancel()
        logger.info("📅 NotificationScheduler parado")
    
    async def check_expired_loop(self):
        """Loop para verificar assinaturas expiradas"""
        while self.running:
            try:
                await self.check_expired_subscriptions()
                await asyncio.sleep(3600)  # Verificar a cada hora
            except Exception as e:
                logger.error(f"Erro no check_expired_loop: {e}")
                await asyncio.sleep(60)
    
    async def send_reminders_loop(self):
        """Loop para enviar lembretes"""
        while self.running:
            try:
                # Calcular tempo até próximas 10h
                now = datetime.now()
                next_run = now.replace(hour=10, minute=0, second=0, microsecond=0)
                if now >= next_run:
                    next_run += timedelta(days=1)
                
                wait_seconds = (next_run - now).total_seconds()
                await asyncio.sleep(wait_seconds)
                
                await self.send_renewal_reminders()
                
            except Exception as e:
                logger.error(f"Erro no send_reminders_loop: {e}")
                await asyncio.sleep(3600)
    
    async def check_expired_subscriptions(self):
        """Verificar e processar assinaturas expiradas"""
        logger.info("🔍 Verificando assinaturas expiradas...")
        
        with get_db_session() as session:
            # Buscar assinaturas expiradas
            expired = session.query(Subscription).filter(
                Subscription.status == 'active',
                Subscription.end_date < datetime.utcnow()
            ).all()
            
            for sub in expired:
                sub.status = 'expired'
                # TODO: Implementar remoção do grupo
                logger.info(f"Assinatura {sub.id} marcada como expirada")
            
            session.commit()
            logger.info(f"✅ {len(expired)} assinaturas processadas")
    
    async def send_renewal_reminders(self):
        """Enviar lembretes de renovação"""
        logger.info("📨 Enviando lembretes de renovação...")
        
        # TODO: Implementar envio de lembretes
        logger.info("✅ Lembretes enviados")
''')
    
    # bot/jobs/__init__.py
    create_file("bot/jobs/__init__.py", '''"""
Jobs agendados do Bot TeleVIP
"""
''')
    
    # bot/jobs/scheduled_tasks.py
    create_file("bot/jobs/scheduled_tasks.py", '''"""
Tarefas agendadas do bot
"""
import logging
from datetime import datetime, timedelta
from telegram.ext import Application

from bot.utils.database import get_db_session
from app.models import Subscription, Group

logger = logging.getLogger(__name__)

def setup_jobs(application: Application):
    """Configurar jobs agendados"""
    job_queue = application.job_queue
    
    if not job_queue:
        logger.warning("⚠️  JobQueue não disponível - jobs não serão agendados")
        return
    
    # Verificar assinaturas expiradas a cada hora
    job_queue.run_repeating(
        check_expired_subscriptions,
        interval=3600,  # 1 hora
        first=10
    )
    
    # Enviar lembretes de renovação diariamente às 10h
    job_queue.run_daily(
        send_renewal_reminders,
        time=datetime.time(10, 0, 0)
    )
    
    logger.info("✅ Jobs agendados configurados")

async def check_expired_subscriptions(context):
    """Verificar e remover assinaturas expiradas"""
    logger.info("🔍 Verificando assinaturas expiradas...")
    
    # TODO: Implementar verificação completa
    logger.info("✅ Verificação concluída")

async def send_renewal_reminders(context):
    """Enviar lembretes de renovação"""
    logger.info("📨 Enviando lembretes de renovação...")
    
    # TODO: Implementar envio de lembretes
    logger.info("✅ Lembretes enviados")
''')
    
    # Criar arquivo de configuração de exemplo
    create_file(".env.bot.example", '''# Configuração do Bot TeleVIP

# Bot Token do Telegram
BOT_TOKEN=seu_bot_token_aqui
BOT_USERNAME=seu_bot_username

# Banco de dados (mesmo do Flask)
DATABASE_URL=sqlite:///instance/televip.db

# Stripe
STRIPE_PUBLIC_KEY=pk_test_...
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Configurações
PLATFORM_FEE=0.01
MIN_WITHDRAWAL=10.0

# URLs da aplicação
APP_URL=https://televip.com
WEBHOOK_URL=https://televip.com/webhooks/telegram
''')
    
    # Criar script de inicialização
    create_file("start_bot.sh", '''#!/bin/bash
# Script para iniciar o Bot TeleVIP

echo "🚀 Iniciando Bot TeleVIP..."

# Ativar ambiente virtual
if [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "⚠️  Ambiente virtual não encontrado!"
    echo "Crie com: python -m venv venv"
    exit 1
fi

# Verificar dependências
echo "📦 Verificando dependências..."
pip install -q python-telegram-bot python-dotenv sqlalchemy

# Executar bot
echo "🤖 Iniciando bot..."
python bot/main.py
''')
    
    # Tornar script executável
    if os.name != 'nt':  # Se não for Windows
        os.chmod('start_bot.sh', 0o755)
    
    # Criar README para o bot
    create_file("bot/README.md", '''# Bot TeleVIP - Sistema Multi-Criador

## 🚀 Início Rápido

1. Configure as variáveis de ambiente:
   ```bash
   cp .env.bot.example .env
   # Edite .env com suas configurações
   ```

2. Instale as dependências:
   ```bash
   pip install python-telegram-bot python-dotenv sqlalchemy stripe
   ```

3. Execute o bot:
   ```bash
   python bot/main.py
   # ou
   ./start_bot.sh
   ```

## 📁 Estrutura

```
bot/
├── main.py              # Arquivo principal
├── handlers/            # Handlers de comandos
│   ├── start.py        # /start e dashboard
│   ├── payment.py      # Processamento de pagamentos
│   ├── subscription.py # Gestão de assinaturas
│   ├── admin.py        # Comandos administrativos
│   └── discovery.py    # Sistema de descoberta
├── keyboards/          # Teclados inline
├── utils/              # Utilitários
│   ├── database.py     # Conexão com DB
│   ├── stripe_integration.py # Integração Stripe
│   └── notifications.py # Sistema de notificações
└── jobs/               # Tarefas agendadas
```

## 🤖 Comandos

### Para Usuários:
- `/start` - Dashboard de assinaturas
- `/status` - Status detalhado
- `/planos` - Planos ativos
- `/descobrir` - Descobrir grupos

### Para Criadores:
- `/setup` - Configurar grupo
- `/stats` - Estatísticas
- `/broadcast` - Mensagem em massa

## 📝 TODOs

- [ ] Implementar dashboard completo em `start.py`
- [ ] Completar fluxo de pagamento em `payment.py`
- [ ] Adicionar sistema de descoberta em `discovery.py`
- [ ] Implementar jobs agendados
- [ ] Adicionar integração PIX
- [ ] Sistema de avaliações
- [ ] Métricas e analytics

## 🔧 Desenvolvimento

Para adicionar novos comandos:

1. Crie o handler em `bot/handlers/`
2. Registre no `main.py`
3. Adicione ao menu de comandos

## 📞 Suporte

Em caso de dúvidas, consulte a documentação principal do projeto.
''')
    
    print("\n✅ Estrutura do Bot TeleVIP criada com sucesso!")
    print("\n📋 Próximos passos:")
    print("1. Configure o arquivo .env com suas credenciais")
    print("2. Instale as dependências: pip install python-telegram-bot python-dotenv sqlalchemy stripe")
    print("3. Execute o bot: python bot/main.py")
    print("\n💡 Os arquivos foram criados com estrutura básica e TODOs para implementação.")
    print("   Substitua o conteúdo conforme a documentação fornecida.")

if __name__ == "__main__":
    main()