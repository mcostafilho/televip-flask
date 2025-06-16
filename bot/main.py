#!/usr/bin/env python3
"""
Bot principal do TeleVIP com melhorias de UX
"""
import os
import sys
import asyncio
import logging
import datetime
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Adicionar o diretório raiz ao path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, JobQueue
from telegram.constants import ParseMode

# Importar handlers melhorados
from bot.handlers.start import start_command, help_command, handle_payment_success
from bot.handlers.payment_stripe import (
    handle_plan_selection, 
    handle_stripe_payment,
    cancel_payment
)
from bot.handlers.subscription import show_plans, check_status, handle_renewal
from bot.handlers.admin import setup_group, show_stats, broadcast_message
from bot.handlers.group_manager import on_new_member, remove_expired_members, send_renewal_reminders
from bot.utils.database import get_db_session
from bot.utils.notifications import NotificationScheduler

# Carregar variáveis de ambiente
load_dotenv()

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class TeleVIPBot:
    def __init__(self):
        self.token = os.getenv('BOT_TOKEN')
        self.username = os.getenv('BOT_USERNAME')
        
        if not self.token:
            raise ValueError("BOT_TOKEN não configurado no .env")
        
        logger.info(f"🤖 Inicializando TeleVIP Bot...")
        
        # Criar aplicação
        self.app = Application.builder().token(self.token).build()
        
        # Criar scheduler de notificações
        self.notification_scheduler = NotificationScheduler(self.app.bot)
        
    def setup_handlers(self):
        """Configurar todos os handlers do bot"""
        logger.info("📋 Configurando handlers...")
        
        # Comandos básicos
        self.app.add_handler(CommandHandler("start", start_command))
        self.app.add_handler(CommandHandler("help", help_command))
        self.app.add_handler(CommandHandler("planos", show_plans))
        self.app.add_handler(CommandHandler("status", check_status))
        
        # Comandos admin
        self.app.add_handler(CommandHandler("setup", setup_group))
        self.app.add_handler(CommandHandler("stats", show_stats))
        self.app.add_handler(CommandHandler("broadcast", broadcast_message))
        
        # Callbacks dos botões
        self.app.add_handler(CallbackQueryHandler(handle_plan_selection, pattern="^plan_"))
        self.app.add_handler(CallbackQueryHandler(handle_stripe_payment, pattern="^stripe_"))
        self.app.add_handler(CallbackQueryHandler(cancel_payment, pattern="^cancel"))
        self.app.add_handler(CallbackQueryHandler(self.close_message, pattern="^close"))
        self.app.add_handler(CallbackQueryHandler(check_status, pattern="^check_status"))
        self.app.add_handler(CallbackQueryHandler(handle_renewal, pattern="^renew_"))
        
        # Handler geral para callbacks não tratados
        self.app.add_handler(CallbackQueryHandler(self.handle_unknown_callback))
        
        # Handler para novos membros no grupo
        self.app.add_handler(MessageHandler(
            filters.StatusUpdate.NEW_CHAT_MEMBERS,
            on_new_member
        ))
        
        logger.info("✅ Handlers configurados com sucesso!")
    
    async def close_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Fechar/deletar mensagem"""
        query = update.callback_query
        await query.answer()
        await query.message.delete()
    
    async def handle_unknown_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler para callbacks não reconhecidos"""
        query = update.callback_query
        await query.answer("🚧 Função em desenvolvimento...", show_alert=True)
        logger.warning(f"Callback não reconhecido: {query.data}")
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Log de erros melhorado"""
        logger.error(f"Erro no update {update}: {context.error}")
        
        # Notificar usuário sobre o erro
        if update and update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "❌ Ocorreu um erro ao processar sua solicitação.\n"
                    "Por favor, tente novamente ou contate o suporte.",
                    parse_mode=ParseMode.MARKDOWN
                )
            except:
                pass
    
    async def post_init(self, application: Application) -> None:
        """Executado após a inicialização do bot"""
        bot_info = await application.bot.get_me()
        logger.info(f"✅ Bot @{bot_info.username} iniciado com sucesso!")
        logger.info(f"   Nome: {bot_info.first_name}")
        logger.info(f"   ID: {bot_info.id}")
        
        # Iniciar scheduler de notificações
        await self.notification_scheduler.start()
        
        # Agendar jobs recorrentes
        job_queue = application.job_queue
        
        # Verificar assinaturas expiradas a cada 6 horas
        job_queue.run_repeating(
            remove_expired_members,
            interval=21600,  # 6 horas
            first=60,  # Começar em 1 minuto
            name='remove_expired'
        )
        
        # Enviar lembretes de renovação 1x por dia às 10h
        job_queue.run_daily(
            send_renewal_reminders,
            time=datetime.time(hour=10, minute=0),
            name='renewal_reminders'
        )
        
        logger.info("📅 Jobs agendados com sucesso")
        
        # Definir comandos no menu do Telegram
        await application.bot.set_my_commands([
            ("start", "Iniciar conversa com o bot"),
            ("planos", "Ver seus planos ativos"),
            ("status", "Verificar status das assinaturas"),
            ("help", "Obter ajuda"),
            ("setup", "Configurar bot no grupo (admin)"),
            ("stats", "Ver estatísticas (admin)")
        ])
        
        logger.info("📱 Comandos registrados no menu do Telegram")
    
    async def post_shutdown(self, application: Application) -> None:
        """Executado ao desligar o bot"""
        logger.info("🛑 Desligando bot...")
        await self.notification_scheduler.stop()
        logger.info("✅ Bot desligado com sucesso")
    
    def run(self):
        """Executar o bot"""
        try:
            # Configurar handlers
            self.setup_handlers()
            
            # Configurar error handler
            self.app.add_error_handler(self.error_handler)
            
            # Configurar callbacks de inicialização e shutdown
            self.app.post_init = self.post_init
            self.app.post_shutdown = self.post_shutdown
            
            # Iniciar bot
            logger.info("🚀 Iniciando TeleVIP Bot...")
            logger.info("   Pressione Ctrl+C para parar")
            logger.info("   Acesse https://t.me/{} para testar".format(self.username or "seu_bot"))
            
            # Run polling
            self.app.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True  # Ignorar mensagens antigas
            )
            
        except Exception as e:
            logger.error(f"❌ Erro ao executar bot: {e}")
            raise

def main():
    """Função principal"""
    try:
        # Mostrar banner
        print("""
╔══════════════════════════════════════╗
║        🤖 TeleVIP Bot v2.0 🤖        ║
║   Sistema de Assinaturas Premium     ║
╚══════════════════════════════════════╝
        """)
        
        bot = TeleVIPBot()
        bot.run()
        
    except KeyboardInterrupt:
        logger.info("⏹️  Bot interrompido pelo usuário")
    except Exception as e:
        logger.error(f"❌ Erro fatal: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()