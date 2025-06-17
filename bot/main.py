#!/usr/bin/env python3
"""
Bot principal do TeleVIP - Sistema Multi-Criador
"""
import os
import sys
import asyncio
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Adicionar o diretório raiz ao path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, filters, ContextTypes
)

# Importar handlers
from bot.handlers.start import start_command, help_command, show_user_dashboard
from bot.handlers.payment import handle_plan_selection, handle_payment_callback, handle_payment_success
from bot.handlers.subscription import (
    status_command, planos_command, handle_renewal
)
from bot.handlers.admin import (
    setup_command, stats_command, broadcast_command,
    handle_join_request, handle_new_chat_members
)
from bot.handlers.discovery import descobrir_command, handle_discover_callback
from bot.handlers.payment_verification import check_payment_status
from bot.utils.database import get_db_session

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
        logger.error("Configure o arquivo .env com BOT_TOKEN=seu_token_aqui")
        sys.exit(1)
    
    # Criar aplicação - CORREÇÃO: sem job_queue para evitar erro de weak reference
    application = (
        Application.builder()
        .token(token)
        .job_queue(None)  # Desabilitar job_queue temporariamente
        .build()
    )
    
    # Registrar handlers
    setup_handlers(application)
    
    # Callback de inicialização
    application.post_init = post_init
    
    # Iniciar bot
    logger.info("🤖 Bot TeleVIP iniciando...")
    logger.info("Pressione Ctrl+C para parar")
    
    try:
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

def setup_handlers(application):
    """Configurar todos os handlers do bot"""
    logger.info("📋 Configurando handlers...")
    
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
    
    # Registrar callbacks específicos
    application.add_handler(CallbackQueryHandler(
        handle_plan_selection, pattern="^plan_"
    ))
    application.add_handler(CallbackQueryHandler(
        handle_payment_callback, pattern="^pay_"
    ))
    application.add_handler(CallbackQueryHandler(
        handle_renewal, pattern="^renew"
    ))
    application.add_handler(CallbackQueryHandler(
        handle_check_status_callback, pattern="^check_status$"
    ))
    application.add_handler(CallbackQueryHandler(
        check_payment_status, pattern="^check_payment_status$"
    ))
    application.add_handler(CallbackQueryHandler(
        handle_discover_callback, pattern="^discover"
    ))
    application.add_handler(CallbackQueryHandler(
        handle_back_callback, pattern="^back_to_start$"
    ))
    application.add_handler(CallbackQueryHandler(
        handle_help_callback, pattern="^help$"
    ))
    application.add_handler(CallbackQueryHandler(
        handle_cancel_callback, pattern="^cancel$"
    ))
    application.add_handler(CallbackQueryHandler(
        handle_categories_callback, pattern="^categor"
    ))
    application.add_handler(CallbackQueryHandler(
        handle_premium_callback, pattern="^premium_groups$"
    ))
    application.add_handler(CallbackQueryHandler(
        handle_new_groups_callback, pattern="^new_groups$"
    ))
    application.add_handler(CallbackQueryHandler(
        handle_cheap_callback, pattern="^cheapest_groups$"
    ))
    
    # Handlers para gerenciar membros do grupo
    application.add_handler(MessageHandler(
        filters.StatusUpdate.NEW_CHAT_MEMBERS,
        handle_new_chat_members
    ))
    
    # Handler geral para callbacks não tratados
    application.add_handler(CallbackQueryHandler(handle_unknown_callback))
    
    logger.info("✅ Handlers configurados com sucesso!")

async def handle_check_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para callback check_status"""
    from bot.handlers.subscription import status_command
    query = update.callback_query
    await query.answer()
    
    # Simular comando /status
    await status_command(update, context)

async def handle_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para voltar ao início"""
    from bot.handlers.start import show_user_dashboard
    query = update.callback_query
    await query.answer()
    
    # Atualizar context para callback
    await show_user_dashboard(update, context)

async def handle_help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para callback help"""
    query = update.callback_query
    await query.answer()
    
    # Mostrar ajuda
    text = """📋 **Central de Ajuda TeleVIP**

**🔸 Comandos para Assinantes:**

/start - Painel principal com suas assinaturas
/status - Status detalhado de todas assinaturas
/planos - Listar seus planos ativos
/descobrir - Explorar novos grupos disponíveis
/help - Mostrar esta mensagem de ajuda

**🔹 Comandos para Criadores:**

/setup - Configurar o bot em seu grupo
/stats - Ver estatísticas detalhadas
/broadcast - Enviar mensagem para assinantes

**💡 Dicas Úteis:**

• 🔔 Ative as notificações para não perder avisos importantes
• 💰 Renove com antecedência e ganhe descontos
• 🔍 Use /descobrir para encontrar conteúdo novo
• 📱 Salve os links dos grupos para acesso rápido

**❓ Perguntas Frequentes:**

**Como assino um grupo?**
Clique no link fornecido pelo criador ou use /descobrir

**Como cancelo uma assinatura?**
As assinaturas não renovam automaticamente

**Posso mudar de plano?**
Sim, quando sua assinatura atual expirar

**É seguro?**
Sim, usamos Stripe para processar pagamentos

**📞 Suporte:**
• Problemas com pagamento: suporte@televip.com
• Dúvidas sobre conteúdo: contate o criador do grupo

🔒 Seus dados estão seguros e protegidos."""
    
    keyboard = [
        [
            InlineKeyboardButton("⬅️ Voltar", callback_data="back_to_start"),
            InlineKeyboardButton("📞 Suporte", url="https://t.me/suporte_televip")
        ]
    ]
    
    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para cancelar operação"""
    query = update.callback_query
    await query.answer("❌ Operação cancelada")
    
    # Voltar ao dashboard
    await handle_back_callback(update, context)

async def handle_categories_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para callback de categorias"""
    from bot.handlers.discovery import handle_discover_callback
    # Redirecionar para o handler de discovery que já trata categorias
    await handle_discover_callback(update, context)

async def handle_premium_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para grupos premium"""
    from bot.handlers.discovery import handle_discover_callback
    await handle_discover_callback(update, context)

async def handle_new_groups_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para grupos novos"""
    from bot.handlers.discovery import handle_discover_callback
    await handle_discover_callback(update, context)

async def handle_cheap_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para grupos baratos"""
    from bot.handlers.discovery import handle_discover_callback
    await handle_discover_callback(update, context)

async def handle_unknown_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para callbacks não reconhecidos"""
    query = update.callback_query
    await query.answer("🚧 Função em desenvolvimento...", show_alert=True)
    logger.warning(f"Callback não reconhecido: {query.data}")

async def post_init(application: Application) -> None:
    """Executado após a inicialização do bot"""
    try:
        bot_info = await application.bot.get_me()
        logger.info(f"✅ Bot @{bot_info.username} iniciado com sucesso!")
        logger.info(f"   Nome: {bot_info.first_name}")
        logger.info(f"   ID: {bot_info.id}")
        
        # Definir comandos no menu do Telegram
        await application.bot.set_my_commands([
            ("start", "Ver suas assinaturas ou assinar novo grupo"),
            ("status", "Status detalhado de todas assinaturas"),
            ("planos", "Ver todos seus planos ativos"),
            ("descobrir", "Explorar novos grupos disponíveis"),
            ("help", "Obter ajuda"),
            ("setup", "Configurar bot no grupo (admin)"),
            ("stats", "Ver estatísticas (admin)")
        ])
        
        logger.info("📱 Comandos registrados no menu do Telegram")
        
        # Nota sobre jobs desabilitados
        logger.warning("⚠️  JobQueue desabilitado temporariamente - tarefas agendadas não estão ativas")
        
    except Exception as e:
        logger.error(f"Erro ao inicializar bot: {e}")

if __name__ == '__main__':
    # Mostrar banner
    print("""
╔══════════════════════════════════════╗
║        🤖 TeleVIP Bot v2.0 🤖        ║
║   Sistema Multi-Criador Premium      ║
╚══════════════════════════════════════╝
    """)
    
    # Verificar configurações
    if not os.getenv('BOT_TOKEN'):
        print("❌ ERRO: BOT_TOKEN não configurado!")
        print("\n📋 Como configurar:")
        print("1. Copie .env.bot.example para .env")
        print("2. Edite .env e adicione seu BOT_TOKEN")
        print("3. Execute novamente: python bot/main.py")
        sys.exit(1)
    
    main()