"""
Handler para comandos /start e /help
"""
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from bot.utils.database import get_db_session
from bot.keyboards.menus import get_main_menu, get_plans_menu
from app.models import Group, Creator

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler do comando /start"""
    user = update.effective_user
    args = context.args
    
    # Verificar se veio com parâmetro de grupo
    if args and args[0].startswith('g_'):
        # Extrair ID do grupo
        group_code = args[0][2:]  # Remove 'g_'
        
        # Buscar grupo no banco
        with get_db_session() as session:
            group = session.query(Group).filter_by(telegram_id=group_code).first()
            
            if not group:
                await update.message.reply_text(
                    "❌ Grupo não encontrado. Verifique o link e tente novamente."
                )
                return
            
            if not group.is_active:
                await update.message.reply_text(
                    "❌ Este grupo não está mais aceitando novas assinaturas."
                )
                return
            
            # Mensagem de boas-vindas personalizada
            welcome_text = f"""
🎉 *Bem-vindo ao {group.name}!*

{group.description or 'Grupo VIP exclusivo com conteúdo premium.'}

✨ *Benefícios do grupo:*
• Acesso exclusivo ao conteúdo
• Suporte direto com o criador
• Atualizações em primeira mão
• Comunidade engajada

💰 *Planos disponíveis:*
"""
            
            # Buscar planos do grupo
            plans = group.pricing_plans.filter_by(is_active=True).all()
            
            for plan in plans:
                welcome_text += f"\n• {plan.name}: R$ {plan.price:.2f}"
            
            welcome_text += "\n\nEscolha um plano para começar:"
            
            # Criar teclado com os planos
            keyboard = get_plans_menu(group.id)
            
            await update.message.reply_text(
                welcome_text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )
    else:
        # Mensagem padrão do bot
        welcome_text = f"""
👋 Olá {user.first_name}!

Eu sou o *TeleVIP Bot*, seu assistente para gerenciar assinaturas de grupos VIP no Telegram.

🤖 *O que eu posso fazer:*
• Processar pagamentos de assinaturas
• Adicionar você aos grupos automaticamente
• Notificar sobre renovações
• Gerenciar seus acessos

📱 *Como funciona:*
1. Você recebe um link de um criador
2. Escolhe o plano desejado
3. Faz o pagamento via PIX
4. É adicionado automaticamente ao grupo

Use /help para ver todos os comandos disponíveis.
"""
        
        keyboard = get_main_menu()
        
        await update.message.reply_text(
            welcome_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler do comando /help"""
    help_text = """
📋 *Comandos Disponíveis:*

👤 *Para Assinantes:*
/start - Iniciar conversa com o bot
/planos - Ver planos disponíveis
/status - Verificar status das assinaturas
/help - Mostrar esta mensagem

👨‍💼 *Para Criadores:*
/setup - Configurar bot no grupo
/stats - Ver estatísticas do grupo
/broadcast - Enviar mensagem aos assinantes

💡 *Dicas:*
• Guarde o comprovante de pagamento
• Ative notificações para não perder avisos
• Em caso de problemas, contate o suporte

🆘 *Suporte:*
Em caso de dúvidas ou problemas, entre em contato com o criador do grupo ou com nosso suporte.
"""
    
    await update.message.reply_text(
        help_text,
        parse_mode=ParseMode.MARKDOWN
    )