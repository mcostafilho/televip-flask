#!/usr/bin/env python3
"""
Bot principal do TeleVIP
Gerencia assinaturas de grupos VIP no Telegram
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
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode

# Importar handlers
from bot.handlers import start, payment, subscription, admin
from bot.utils.database import get_db_session
from bot.keyboards.menus import get_main_menu, get_plans_menu

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
        
        logger.info(f"Inicializando bot com token: {self.token[:10]}...")
        
        # Criar aplicação - NOVA API
        self.app = Application.builder().token(self.token).build()
        
    def setup_handlers(self):
        """Configurar todos os handlers do bot"""
        logger.info("Configurando handlers...")
        
        # Comandos básicos
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("planos", self.show_plans))
        self.app.add_handler(CommandHandler("status", self.check_status))
        
        # Comandos admin
        self.app.add_handler(CommandHandler("setup", self.setup_group))
        self.app.add_handler(CommandHandler("stats", self.show_stats))
        
        # Callbacks (botões)
        self.app.add_handler(CallbackQueryHandler(self.button_callback))
        
        logger.info("Handlers configurados com sucesso!")
        
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler do comando /start"""
        user = update.effective_user
        logger.info(f"Comando /start de {user.username} ({user.id})")
        
        welcome_text = f"""
👋 Olá {user.first_name}!

Eu sou o *TeleVIP Bot*, seu assistente para gerenciar assinaturas de grupos VIP no Telegram.

🤖 *O que eu posso fazer:*
• Processar pagamentos de assinaturas
• Adicionar você aos grupos automaticamente
• Notificar sobre renovações
• Gerenciar seus acessos

Use /help para ver todos os comandos disponíveis.
"""
        
        keyboard = [
            [
                InlineKeyboardButton("📋 Meus Planos", callback_data="my_plans"),
                InlineKeyboardButton("❓ Ajuda", callback_data="help")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            welcome_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler do comando /help"""
        help_text = """
📋 *Comandos Disponíveis:*

👤 *Para Assinantes:*
/start - Iniciar conversa com o bot
/planos - Ver seus planos ativos
/status - Verificar status das assinaturas
/help - Mostrar esta mensagem

👨‍💼 *Para Criadores:*
/setup - Configurar bot no grupo
/stats - Ver estatísticas
"""
        
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
    
    async def show_plans(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Mostrar planos do usuário"""
        user = update.effective_user
        
        with get_db_session() as session:
            from app.models import Subscription
            
            # Buscar assinaturas do usuário
            subscriptions = session.query(Subscription).filter_by(
                telegram_user_id=str(user.id),
                status='active'
            ).all()
            
            if not subscriptions:
                await update.message.reply_text(
                    "📭 Você ainda não tem nenhuma assinatura ativa.\n\n"
                    "Para assinar um grupo, use o link fornecido pelo criador."
                )
                return
            
            # Listar assinaturas
            message = "📋 *Suas Assinaturas Ativas:*\n\n"
            
            for sub in subscriptions:
                group = sub.group
                plan = sub.plan
                days_left = (sub.end_date - datetime.utcnow()).days
                
                message += f"📱 *{group.name}*\n"
                message += f"   • Plano: {plan.name}\n"
                message += f"   • Válido até: {sub.end_date.strftime('%d/%m/%Y')}\n"
                message += f"   • Dias restantes: {days_left}\n\n"
            
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
    
    async def check_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Verificar status das assinaturas"""
        await update.message.reply_text("🔄 Verificando suas assinaturas...")
        await self.show_plans(update, context)
    
    async def setup_group(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Configurar bot no grupo"""
        chat = update.effective_chat
        
        if chat.type == 'private':
            await update.message.reply_text(
                "❌ Este comando deve ser usado dentro de um grupo!\n\n"
                "1. Adicione o bot ao seu grupo\n"
                "2. Promova o bot a administrador\n"
                "3. Use /setup dentro do grupo"
            )
            return
        
        setup_text = f"""
✅ *Grupo Detectado!*

🆔 *ID do Grupo:* `{chat.id}`
📱 *Nome:* {chat.title}

*Próximos passos:*
1. Copie o ID acima
2. Acesse https://televip.com ou http://localhost:5000
3. Crie/edite seu grupo
4. Cole este ID no campo "ID do Grupo no Telegram"

Após configurar, você receberá um link para compartilhar com seus seguidores!
"""
        
        await update.message.reply_text(setup_text, parse_mode=ParseMode.MARKDOWN)
    
    async def show_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Mostrar estatísticas (comando admin)"""
        user = update.effective_user
        
        # Verificar se é admin
        with get_db_session() as session:
            from app.models import Creator
            
            creator = session.query(Creator).filter_by(
                telegram_id=str(user.id)
            ).first()
            
            if not creator:
                await update.message.reply_text(
                    "❌ Você não está cadastrado como criador!\n"
                    "Acesse o painel web para se cadastrar."
                )
                return
            
            # Estatísticas básicas
            stats_text = f"""
📊 *Estatísticas de {creator.name}*

💰 Saldo: R$ {creator.balance:.2f}
📈 Total Ganho: R$ {creator.total_earned:.2f}
📱 Grupos: {creator.groups.count()}

Para ver estatísticas detalhadas, acesse o painel web.
"""
            
            await update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler para callbacks dos botões"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "my_plans":
            # Converter para mensagem para usar show_plans
            update.message = query.message
            await self.show_plans(update, context)
        elif query.data == "help":
            update.message = query.message
            await self.help_command(update, context)
        else:
            await query.edit_message_text("🚧 Função em desenvolvimento...")
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Log de erros"""
        logger.error(f"Erro no update {update}: {context.error}")
    
    async def post_init(self, application: Application) -> None:
        """Executado após a inicialização do bot"""
        bot_info = await application.bot.get_me()
        logger.info(f"🤖 Bot @{bot_info.username} iniciado com sucesso!")
        logger.info(f"   Nome: {bot_info.first_name}")
        logger.info(f"   ID: {bot_info.id}")
    
    def run(self):
        """Executar o bot"""
        try:
            # Configurar handlers
            self.setup_handlers()
            
            # Configurar error handler
            self.app.add_error_handler(self.error_handler)
            
            # Configurar post_init
            self.app.post_init = self.post_init
            
            # Iniciar bot
            logger.info("🚀 Iniciando TeleVIP Bot...")
            logger.info("   Pressione Ctrl+C para parar")
            
            # Run polling - NOVA API
            self.app.run_polling(allowed_updates=Update.ALL_TYPES)
            
        except Exception as e:
            logger.error(f"Erro ao executar bot: {e}")
            raise

def main():
    """Função principal"""
    try:
        bot = TeleVIPBot()
        bot.run()
    except KeyboardInterrupt:
        logger.info("Bot interrompido pelo usuário")
    except Exception as e:
        logger.error(f"Erro fatal: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()