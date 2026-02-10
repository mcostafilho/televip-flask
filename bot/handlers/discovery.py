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
            
            # Adicionar botões de navegação
            keyboard.extend([
                [
                    InlineKeyboardButton("🏆 Premium", callback_data="premium_groups"),
                    InlineKeyboardButton("📊 Categorias", callback_data="categories")
                ],
                [
                    InlineKeyboardButton("🆕 Novos", callback_data="new_groups"),
                    InlineKeyboardButton("💰 Mais Baratos", callback_data="cheapest_groups")
                ],
                [
                    InlineKeyboardButton("🔄 Atualizar", callback_data="refresh_discovery")
                ]
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
    """Handler para callbacks de descoberta - CORRIGIDO"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "discover" or query.data == "refresh_discovery":
        # Chamar show_popular_groups diretamente
        await show_popular_groups(update, context)
    
    elif query.data == "categories":
        await show_categories(update, context)
    
    elif query.data == "premium_groups":
        await show_premium_groups(update, context)
    
    elif query.data == "new_groups":
        await show_new_groups(update, context)
    
    elif query.data == "cheapest_groups":
        await show_cheapest_groups(update, context)

async def show_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostrar categorias de grupos"""
    query = update.callback_query
    
    text = """
📂 **Categorias**

Escolha uma categoria para explorar:
"""
    
    keyboard = [
        [
            InlineKeyboardButton("🎓 Educação", callback_data="cat_educacao"),
            InlineKeyboardButton("💪 Fitness", callback_data="cat_fitness")
        ],
        [
            InlineKeyboardButton("💰 Finanças", callback_data="cat_financas"),
            InlineKeyboardButton("🎮 Games", callback_data="cat_games")
        ],
        [
            InlineKeyboardButton("🎵 Música", callback_data="cat_musica"),
            InlineKeyboardButton("🎨 Arte", callback_data="cat_arte")
        ],
        [
            InlineKeyboardButton("⬅️ Voltar", callback_data="discover")
        ]
    ]
    
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_premium_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostrar grupos premium (mais caros)"""
    query = update.callback_query
    user = update.effective_user
    
    with get_db_session() as session:
        # Buscar grupos com planos mais caros (excluir criadores bloqueados)
        groups_with_prices = []

        groups = session.query(Group).join(Creator).filter(
            Group.is_active == True,
            Creator.is_blocked == False
        ).all()

        for group in groups:
            max_price_plan = session.query(PricingPlan).filter_by(
                group_id=group.id,
                is_active=True
            ).order_by(PricingPlan.price.desc()).first()
            
            if max_price_plan:
                groups_with_prices.append((group, max_price_plan.price))
        
        # Ordenar por preço
        groups_with_prices.sort(key=lambda x: x[1], reverse=True)
        
        text = """
🏆 **Grupos Premium**

Os grupos VIP mais exclusivos:

"""
        keyboard = []
        
        for group, max_price in groups_with_prices[:5]:
            text += f"💎 **{group.name}**\n"
            text += f"   👥 {group.total_subscribers or 0} assinantes\n"
            text += f"   💰 Até R$ {max_price:.2f}\n\n"
            
            bot_username = context.bot.username
            keyboard.append([
                InlineKeyboardButton(
                    f"💎 {group.name}",
                    url=f"https://t.me/{bot_username}?start=g_{group.invite_slug}"
                )
            ])
        
        keyboard.append([
            InlineKeyboardButton("⬅️ Voltar", callback_data="discover")
        ])
        
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard),
            disable_web_page_preview=True
        )

async def show_new_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostrar grupos mais recentes"""
    query = update.callback_query
    
    with get_db_session() as session:
        # Buscar grupos mais recentes (excluir criadores bloqueados)
        groups = session.query(Group).join(Creator).filter(
            Group.is_active == True,
            Creator.is_blocked == False
        ).order_by(Group.created_at.desc()).limit(5).all()
        
        text = """
🆕 **Grupos Novos**

Grupos recém-chegados na plataforma:

"""
        keyboard = []
        
        for group in groups:
            # Buscar plano mais barato
            cheapest_plan = session.query(PricingPlan).filter_by(
                group_id=group.id,
                is_active=True
            ).order_by(PricingPlan.price).first()
            
            if cheapest_plan:
                days_since = (datetime.utcnow() - group.created_at).days
                
                text += f"🌟 **{group.name}**\n"
                text += f"   📅 Há {days_since} dias\n"
                text += f"   💰 A partir de R$ {cheapest_plan.price:.2f}\n\n"
                
                bot_username = context.bot.username
                keyboard.append([
                    InlineKeyboardButton(
                        f"🌟 {group.name}",
                        url=f"https://t.me/{bot_username}?start=g_{group.invite_slug}"
                    )
                ])
        
        keyboard.append([
            InlineKeyboardButton("⬅️ Voltar", callback_data="discover")
        ])
        
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard),
            disable_web_page_preview=True
        )

async def show_cheapest_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostrar grupos mais baratos"""
    query = update.callback_query
    
    with get_db_session() as session:
        # Buscar grupos com planos mais baratos (excluir criadores bloqueados)
        groups_with_prices = []

        groups = session.query(Group).join(Creator).filter(
            Group.is_active == True,
            Creator.is_blocked == False
        ).all()
        
        for group in groups:
            min_price_plan = session.query(PricingPlan).filter_by(
                group_id=group.id,
                is_active=True
            ).order_by(PricingPlan.price).first()
            
            if min_price_plan:
                groups_with_prices.append((group, min_price_plan.price))
        
        # Ordenar por preço (mais barato primeiro)
        groups_with_prices.sort(key=lambda x: x[1])
        
        text = """
💰 **Grupos Mais Acessíveis**

Ótimas opções com preços baixos:

"""
        keyboard = []
        
        for group, min_price in groups_with_prices[:5]:
            text += f"✨ **{group.name}**\n"
            text += f"   👥 {group.total_subscribers or 0} assinantes\n"
            text += f"   💵 A partir de R$ {min_price:.2f}\n\n"
            
            bot_username = context.bot.username
            keyboard.append([
                InlineKeyboardButton(
                    f"✨ {group.name}",
                    url=f"https://t.me/{bot_username}?start=g_{group.invite_slug}"
                )
            ])
        
        keyboard.append([
            InlineKeyboardButton("⬅️ Voltar", callback_data="discover")
        ])
        
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard),
            disable_web_page_preview=True
        )