#!/usr/bin/env python3
"""
Bot principal do TeleVIP - Sistema Multi-Criador
CORREÇÃO: Problema de weak reference com Application
"""
import os
import sys
import io
import asyncio
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Carregar variáveis de ambiente ANTES de qualquer import que use env vars
load_dotenv()

# CORREÇÃO DE ENCODING
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Adicionar o diretório raiz ao path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, JobQueue
)

# Importar handlers
from bot.handlers.start import start_command, show_user_dashboard
from bot.handlers.payment import (
    start_payment, handle_payment_method,
    list_user_subscriptions, handle_payment_success,
    check_payment_status, handle_payment_error
)
from bot.handlers.subscription import (
    status_command, handle_renewal,
    cancel_subscription, confirm_cancel_subscription,
    reactivate_subscription
)
from bot.handlers.admin import (
    setup_command, stats_command, broadcast_command,
    handle_join_request, handle_new_chat_members,
    handle_broadcast_to_group, handle_broadcast_confirm, handle_cancel_broadcast
)
from bot.handlers.payment_verification import check_payment_status
from bot.utils.database import get_db_session

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# HANDLERS ADICIONAIS QUE ESTAVAM FALTANDO

async def handle_continue_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para continuar para o menu principal"""
    query = update.callback_query
    await query.answer()
    
    # Marcar para pular verificação de pendentes temporariamente
    context.user_data['skip_pending_check'] = True
    await show_user_dashboard(update, context)
    # Remover flag após mostrar
    context.user_data.pop('skip_pending_check', None)

async def handle_payment_error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para erros de pagamento"""
    query = update.callback_query
    await query.answer("❌ Erro no processamento", show_alert=True)
    
    text = """
❌ **Erro no Processamento**

Houve um erro ao processar sua solicitação.

Por favor, tente novamente ou entre em contato com o suporte.
"""
    
    keyboard = [[
        InlineKeyboardButton("🔄 Tentar Novamente", callback_data="back_to_start"),
        InlineKeyboardButton("📞 Suporte", url="https://t.me/suporte_televip")
    ]]
    
    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_check_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para verificar status via callback"""
    await status_command(update, context)

async def handle_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para voltar ao menu principal"""
    await show_user_dashboard(update, context)

async def handle_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para cancelar operação"""
    query = update.callback_query
    await query.answer("❌ Operação cancelada")
    
    # Voltar ao dashboard
    await handle_back_callback(update, context)


async def handle_retry_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para tentar pagamento novamente"""
    query = update.callback_query
    await query.answer("🔄 Redirecionando...")
    
    # Limpar dados antigos
    context.user_data.pop('checkout', None)
    context.user_data.pop('stripe_session_id', None)
    
    # Voltar ao início
    await handle_back_callback(update, context)

async def handle_unknown_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para callbacks não reconhecidos"""
    query = update.callback_query
    await query.answer("Use /start para voltar ao menu principal.", show_alert=True)
    logger.warning(f"Callback não reconhecido: {query.data}")

async def post_init(application: Application) -> None:
    """Executado após a inicialização do bot"""
    try:
        bot_info = await application.bot.get_me()
        logger.info(f"✅ Bot @{bot_info.username} iniciado com sucesso!")
        logger.info(f"Bot ID: {bot_info.id}")
        logger.info(f"Nome: {bot_info.first_name}")

        # Iniciar tarefas agendadas (controle de assinaturas)
        from bot.jobs.scheduled_tasks import setup_jobs
        setup_jobs(application)

    except Exception as e:
        logger.error(f"Erro ao obter informações do bot: {e}")

def setup_handlers(application: Application) -> None:
    """Configurar todos os handlers do bot"""
    logger.info("📋 Configurando handlers...")
    
    # Comandos principais
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("status", status_command))

    # Comandos administrativos
    application.add_handler(CommandHandler("setup", setup_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    
    # Callbacks de pagamento
    application.add_handler(CallbackQueryHandler(start_payment, pattern=r"^plan_\d+_\d+$"))
    application.add_handler(CallbackQueryHandler(handle_payment_method, pattern=r"^pay_stripe$"))
    application.add_handler(CallbackQueryHandler(check_payment_status, pattern="^check_payment_status$"))
    application.add_handler(CallbackQueryHandler(handle_payment_error, pattern="^payment_error$"))
    application.add_handler(CallbackQueryHandler(handle_retry_payment, pattern="^retry_payment$"))
        # Callbacks de navegação
    application.add_handler(CallbackQueryHandler(handle_back_callback, pattern="^back_to_start$"))
    application.add_handler(CallbackQueryHandler(handle_cancel_callback, pattern="^cancel$"))
    application.add_handler(CallbackQueryHandler(handle_check_status_callback, pattern="^check_status$"))
    application.add_handler(CallbackQueryHandler(handle_continue_to_menu, pattern="^continue_to_menu$"))
    
    # Callbacks de renovação
    application.add_handler(CallbackQueryHandler(handle_renewal, pattern=r"^renew_\d+$"))

    # Callbacks de cancelamento de assinatura
    application.add_handler(CallbackQueryHandler(cancel_subscription, pattern=r"^cancel_sub_\d+$"))
    application.add_handler(CallbackQueryHandler(confirm_cancel_subscription, pattern=r"^confirm_cancel_sub_\d+$"))
    application.add_handler(CallbackQueryHandler(reactivate_subscription, pattern=r"^reactivate_sub_\d+$"))

    # Callbacks de broadcast
    application.add_handler(CallbackQueryHandler(handle_broadcast_to_group, pattern=r"^broadcast_to_\d+$"))
    application.add_handler(CallbackQueryHandler(handle_broadcast_confirm, pattern=r"^broadcast_confirm$"))
    application.add_handler(CallbackQueryHandler(handle_cancel_broadcast, pattern=r"^cancel_broadcast$"))

    # Handlers de grupo
    application.add_handler(MessageHandler(
        filters.StatusUpdate.NEW_CHAT_MEMBERS,
        handle_new_chat_members
    ))
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.StatusUpdate.CHAT_CREATED,
        handle_join_request
    ))

    # Handler genérico para callbacks não reconhecidos (deve ser o último)
    application.add_handler(CallbackQueryHandler(handle_unknown_callback))
    
    logger.info("✅ Handlers configurados com sucesso!")

def main():
    """Função principal do bot"""
    # Token do bot
    bot_token = os.getenv('BOT_TOKEN') or os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not bot_token:
        logger.error("❌ BOT_TOKEN não configurado!")
        return
    
    try:
        # CORREÇÃO: Criar aplicação sem job_queue se houver problema
        try:
            # Tentar criar normalmente
            application = Application.builder().token(bot_token).build()
        except TypeError as e:
            # Se falhar, criar sem job_queue
            logger.warning("Criando aplicação sem job_queue devido a erro de weak reference")
            application = Application.builder().token(bot_token).job_queue(None).build()
        
        # Configurar handlers
        setup_handlers(application)
        
        # Adicionar callback de inicialização
        application.post_init = post_init
        
        # Iniciar bot
        logger.info("🤖 Bot TeleVIP iniciando...")
        logger.info("Pressione Ctrl+C para parar")
        
        # Executar bot
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )
        
    except Exception as e:
        logger.error(f"Erro ao iniciar bot: {e}", exc_info=True)
        raise

if __name__ == '__main__':
    main()