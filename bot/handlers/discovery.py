# bot/handlers/discovery.py
"""
Handler para descoberta de grupos
CORREÇÃO: Remover tentativa de modificar callback_query
"""
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from bot.utils.database import get_db_session
from app.models import Group, PricingPlan, Subscription, Creator

logger = logging.getLogger(__name__)

async def descobrir_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando para descobrir grupos disponíveis"""
    await show_popular_groups(update, context)

async def show_popular_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostrar grupos populares disponíveis"""
    # Detectar se é comando ou callback
    if update.callback_query:
        message = update.callback_query.message
        is_callback = True
    else:
        message = update.message
        is_callback = False
    
    user = update.effective_user
    
    with get_db_session() as session:
        # Buscar grupos ativos (excluir criadores bloqueados)
        groups = session.query(Group).join(Creator).filter(
            Group.is_active == True,
            Creator.is_blocked == False
        ).order_by(Group.total_subscribers.desc()).limit(10).all()
        
        if not groups:
            text = """
😔 **Nenhum Grupo Disponível**

Ainda não há grupos disponíveis no momento.

💡 **Dica:** Se você é criador de conteúdo, cadastre seu grupo!

🔗 Acesse: https://televip.app/register
"""
            keyboard = [
                [InlineKeyboardButton("🏠 Menu Principal", callback_data="back_to_start")]
            ]
        else:
            text = """
🔍 **Grupos Disponíveis**

Explore os grupos VIP mais populares:

"""
            keyboard = []
            
            for group in groups[:5]:
                # Buscar plano mais barato
                cheapest_plan = session.query(PricingPlan).filter_by(
                    group_id=group.id,
                    is_active=True
                ).order_by(PricingPlan.price).first()
                
                if cheapest_plan:
                    # Adicionar informações do grupo
                    text += f"📌 **{group.name}**\n"
                    if group.description:
                        text += f"   {group.description[:100]}...\n" if len(group.description) > 100 else f"   {group.description}\n"
                    text += f"   👥 {group.total_subscribers or 0} assinantes\n"
                    text += f"   💰 A partir de R$ {cheapest_plan.price:.2f}\n\n"
                    
                    # Adicionar botão
                    bot_username = context.bot.username
                    keyboard.append([
                        InlineKeyboardButton(
                            f"📍 {group.name}",
                            url=f"https://t.me/{bot_username}?start=g_{group.invite_slug}"
                        )
                    ])
            
            # Botão para voltar ao menu
            keyboard.append([
                InlineKeyboardButton("🏠 Menu Principal", callback_data="back_to_start")
            ])
        
        # Responder com edit ou send baseado no tipo
        if is_callback:
            await message.edit_text(
                text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(keyboard),
                disable_web_page_preview=True
            )
        else:
            await message.reply_text(
                text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(keyboard),
                disable_web_page_preview=True
            )

async def handle_discover_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para callbacks de descoberta"""
    query = update.callback_query
    await query.answer()
    await show_popular_groups(update, context)