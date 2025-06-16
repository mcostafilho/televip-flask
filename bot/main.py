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
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
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
    format='%(asctime)s - **%(name)s** - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Variáveis globais para o bot
notification_scheduler = None

def create_application():
    """Criar e configurar a aplicação do bot"""
    token = os.getenv('BOT_TOKEN')
    
    if not token:
        raise ValueError("BOT_TOKEN não configurado no .env")
    
    logger.info("🤖 Inicializando TeleVIP Bot...")
    
    # Criar aplicação SEM JobQueue para evitar o erro de weak reference
    application = (
        Application.builder()
        .token(token)
        .job_queue(None)  # Desabilitar JobQueue temporariamente
        .build()
    )
    
    # Configurar handlers
    setup_handlers(application)
    
    # Configurar callbacks de inicialização e shutdown
    application.post_init = post_init
    application.post_shutdown = post_shutdown
    application.add_error_handler(error_handler)
    
    return application

def setup_handlers(application):
    """Configurar todos os handlers do bot"""
    logger.info("📋 Configurando handlers...")
    
    # Comandos básicos
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("planos", show_plans))
    application.add_handler(CommandHandler("status", check_status))
    
    # Comandos admin
    application.add_handler(CommandHandler("setup", setup_group))
    application.add_handler(CommandHandler("stats", show_stats))
    application.add_handler(CommandHandler("broadcast", broadcast_message))
    
    # Callbacks dos botões
    application.add_handler(CallbackQueryHandler(handle_plan_selection, pattern="^plan_"))
    application.add_handler(CallbackQueryHandler(handle_stripe_payment, pattern="^stripe_"))
    application.add_handler(CallbackQueryHandler(cancel_payment, pattern="^cancel"))
    application.add_handler(CallbackQueryHandler(close_message, pattern="^close"))
    application.add_handler(CallbackQueryHandler(check_status, pattern="^check_status"))
    application.add_handler(CallbackQueryHandler(handle_renewal, pattern="^renew_"))
    
    # Handler geral para callbacks não tratados
    application.add_handler(CallbackQueryHandler(handle_unknown_callback))
    
    # Handler para novos membros no grupo
    application.add_handler(MessageHandler(
        filters.StatusUpdate.NEW_CHAT_MEMBERS,
        on_new_member
    ))
    
    logger.info("✅ Handlers configurados com sucesso!")

async def close_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fechar/deletar mensagem"""
    query = update.callback_query
    await query.answer()
    await query.message.delete()

async def handle_unknown_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para callbacks não reconhecidos"""
    query = update.callback_query
    await query.answer("🚧 Função em desenvolvimento...", show_alert=True)
    logger.warning(f"Callback não reconhecido: {query.data}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

async def post_init(application: Application) -> None:
    """Executado após a inicialização do bot"""
    global notification_scheduler
    
    bot_info = await application.bot.get_me()
    logger.info(f"✅ Bot @{bot_info.username} iniciado com sucesso!")
    logger.info(f"   Nome: {bot_info.first_name}")
    logger.info(f"   ID: {bot_info.id}")
    
    # Criar e iniciar scheduler de notificações
    notification_scheduler = NotificationScheduler(application.bot)
    await notification_scheduler.start()
    
    # Nota sobre JobQueue desabilitado
    logger.warning("⚠️ JobQueue desabilitado temporariamente - tarefas agendadas serão executadas pelo NotificationScheduler")
    
    # O NotificationScheduler cuidará das tarefas agendadas
    # Ele usa asyncio.create_task internamente em vez do JobQueue
    
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

async def post_shutdown(application: Application) -> None:
    """Executado ao desligar o bot"""
    global notification_scheduler
    
    logger.info("🛑 Desligando bot...")
    
    if notification_scheduler:
        await notification_scheduler.stop()
    
    logger.info("✅ Bot desligado com sucesso")

def main():
    """Função principal"""
    try:
        # Verificar conexão com banco de dados
        try:
            # Tentar importar de diferentes formas para compatibilidade
            try:
                from app import create_app
                from app.extensions import db
            except ImportError:
                try:
                    from app import create_app, db
                except ImportError:
                    from app import create_app
                    db = None
            
            app = create_app()
            if hasattr(app, 'config'):
                db_url = app.config.get('SQLALCHEMY_DATABASE_URI', 'Não configurado')
                logger.info(f"Bot usando banco de dados: {db_url}")
        except Exception as e:
            logger.warning(f"Não foi possível verificar a configuração do banco: {e}")
        
        # Mostrar banner
        print("""
╔══════════════════════════════════════╗
║        🤖 TeleVIP Bot v2.0 🤖        ║
║   Sistema de Assinaturas Premium     ║
╚══════════════════════════════════════╝
        """)
        
        # Criar aplicação
        application = create_application()
        
        # Obter username do bot (opcional)
        username = os.getenv('BOT_USERNAME')
        
        # Iniciar bot
        logger.info("🚀 Iniciando TeleVIP Bot...")
        logger.info("   Pressione Ctrl+C para parar")
        
        if username:
            logger.info(f"   Acesse https://t.me/{username} para testar")
        
        # Run polling
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True  # Ignorar mensagens antigas
        )
        
    except KeyboardInterrupt:
        logger.info("⏹️  Bot interrompido pelo usuário")
    except Exception as e:
        logger.error(f"❌ Erro fatal: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()