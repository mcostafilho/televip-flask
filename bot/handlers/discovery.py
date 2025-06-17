"""
Sistema de descoberta de grupos
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from sqlalchemy import func, and_

from bot.utils.database import get_db_session
from app.models import Group, Subscription, PricingPlan, Creator

logger = logging.getLogger(__name__)

async def descobrir_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /descobrir - mostrar grupos populares"""
    await show_popular_groups(update, context)

async def show_popular_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostrar grupos mais populares com informações detalhadas"""
    
    # Detectar se veio de comando ou callback
    if update.callback_query:
        message = update.callback_query.message
        await update.callback_query.answer()
    else:
        message = update.message
    
    with get_db_session() as session:
        # Query para buscar grupos com estatísticas
        groups_data = []
        
        # Buscar grupos ativos
        groups = session.query(Group).filter_by(is_active=True).all()
        
        for group in groups:
            # Contar assinantes ativos
            subscriber_count = session.query(Subscription).filter_by(
                group_id=group.id,
                status='active'
            ).count()
            
            # Buscar menor preço
            min_price = session.query(func.min(PricingPlan.price)).filter_by(
                group_id=group.id,
                is_active=True
            ).scalar()
            
            if min_price and subscriber_count > 0:  # Só mostrar grupos com planos e assinantes
                # Calcular rating simulado (implementar sistema real depois)
                rating = min(5.0, 4.0 + (subscriber_count / 100))
                
                groups_data.append({
                    'group': group,
                    'subscribers': subscriber_count,
                    'min_price': min_price,
                    'rating': rating
                })
        
        # Ordenar por número de assinantes
        groups_data.sort(key=lambda x: x['subscribers'], reverse=True)
        groups_data = groups_data[:10]  # Top 10
        
        if not groups_data:
            text = """
🔍 **Descobrir Grupos**

😔 Ainda não há grupos disponíveis no momento.

Volte em breve ou peça para seu criador favorito se cadastrar!

💡 **Dica:** Se você é criador de conteúdo, entre em contato para cadastrar seu grupo.
"""
            await message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
            return
        
        # Construir mensagem
        text = "🔥 **Grupos em Alta**\n\n"
        text += "Explore os melhores grupos VIP do Telegram:\n\n"
        
        keyboard = []
        
        for i, data in enumerate(groups_data, 1):
            group = data['group']
            creator = group.creator
            
            # Emoji baseado na posição
            if i == 1:
                position_emoji = "🥇"
            elif i == 2:
                position_emoji = "🥈"
            elif i == 3:
                position_emoji = "🥉"
            else:
                position_emoji = f"{i}."
            
            text += f"{position_emoji} **{group.name}**\n"
            text += f"   👤 @{creator.username or creator.name}\n"
            text += f"   ⭐ {data['rating']:.1f}/5.0 ({data['subscribers']} assinantes)\n"
            text += f"   💰 A partir de R$ {data['min_price']:.2f}\n"
            
            # Adicionar descrição resumida
            if group.description:
                desc = group.description[:60] + "..." if len(group.description) > 60 else group.description
                text += f"   📝 {desc}\n"
            
            text += "\n"
            
            # Botão para cada grupo
            button_text = f"📍 Ver {group.name[:20]}{'...' if len(group.name) > 20 else ''}"
            keyboard.append([
                InlineKeyboardButton(
                    button_text,
                    url=f"https://t.me/{context.bot.username}?start=g_{group.telegram_id}"
                )
            ])
        
        # Adicionar estatísticas gerais
        total_groups = len(groups)
        total_creators = session.query(Creator).filter_by(is_active=True).count()
        
        text += f"\n📊 **Estatísticas da Plataforma:**\n"
        text += f"• {total_groups} grupos disponíveis\n"
        text += f"• {total_creators} criadores ativos\n"
        text += f"• Novos grupos toda semana!\n"
        
        # Botões adicionais
        keyboard.extend([
            [
                InlineKeyboardButton("🏷️ Por Categoria", callback_data="categories"),
                InlineKeyboardButton("💎 Premium", callback_data="premium_groups")
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
        if update.callback_query:
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
    
    if query.data == "discover" or query.data == "refresh_discovery":
        # Simular comando /descobrir
        update.callback_query = query
        await show_popular_groups(update, context)
    
    elif query.data == "categories":
        await show_categories(update, context)
    
    elif query.data == "premium_groups":
        await show_premium_groups(update, context)
    
    elif query.data == "new_groups":
        await show_new_groups(update, context)
    
    elif query.data == "cheapest_groups":
        await show_cheapest_groups(update, context)
    
    elif query.data.startswith("category_"):
        category = query.data.replace("category_", "")
        await show_groups_by_category(update, context, category)

async def show_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostrar categorias de grupos"""
    query = update.callback_query
    
    # Categorias disponíveis (futuro: pegar do banco)
    categories = [
        ("💹", "trading", "Trading e Investimentos"),
        ("🎮", "gaming", "Games e eSports"),
        ("📚", "education", "Educação e Cursos"),
        ("💪", "fitness", "Fitness e Saúde"),
        ("🎨", "creative", "Arte e Criatividade"),
        ("💻", "tech", "Tecnologia"),
        ("🎵", "music", "Música e Entretenimento"),
        ("📸", "photo", "Fotografia"),
        ("🍳", "food", "Culinária"),
        ("✈️", "travel", "Viagens")
    ]
    
    text = "🏷️ **Categorias**\n\n"
    text += "Escolha uma categoria para explorar:\n"
    
    keyboard = []
    
    # Criar botões em pares
    for i in range(0, len(categories), 2):
        row = []
        for j in range(2):
            if i + j < len(categories):
                emoji, key, name = categories[i + j]
                row.append(
                    InlineKeyboardButton(
                        f"{emoji} {name}",
                        callback_data=f"category_{key}"
                    )
                )
        keyboard.append(row)
    
    keyboard.append([
        InlineKeyboardButton("⬅️ Voltar", callback_data="discover")
    ])
    
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_premium_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostrar grupos premium (mais caros/exclusivos)"""
    query = update.callback_query
    
    with get_db_session() as session:
        # Buscar grupos com planos mais caros
        premium_groups = []
        
        groups = session.query(Group).filter_by(is_active=True).all()
        
        for group in groups:
            # Buscar plano mais caro
            max_price = session.query(func.max(PricingPlan.price)).filter_by(
                group_id=group.id,
                is_active=True
            ).scalar()
            
            if max_price and max_price >= 100:  # Premium = R$ 100+
                subscriber_count = session.query(Subscription).filter_by(
                    group_id=group.id,
                    status='active'
                ).count()
                
                premium_groups.append({
                    'group': group,
                    'max_price': max_price,
                    'subscribers': subscriber_count
                })
        
        # Ordenar por preço
        premium_groups.sort(key=lambda x: x['max_price'], reverse=True)
        premium_groups = premium_groups[:5]
        
        if not premium_groups:
            text = "💎 **Grupos Premium**\n\n"
            text += "Nenhum grupo premium disponível no momento."
        else:
            text = "💎 **Grupos Premium**\n\n"
            text += "Os grupos mais exclusivos da plataforma:\n\n"
            
            for data in premium_groups:
                group = data['group']
                creator = group.creator
                
                text += f"👑 **{group.name}**\n"
                text += f"   👤 @{creator.username or creator.name}\n"
                text += f"   💰 Até R$ {data['max_price']:.2f}\n"
                text += f"   👥 {data['subscribers']} membros VIP\n\n"
        
        keyboard = [[
            InlineKeyboardButton("⬅️ Voltar", callback_data="discover")
        ]]
        
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def show_new_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostrar grupos mais recentes"""
    query = update.callback_query
    
    with get_db_session() as session:
        # Buscar grupos criados nos últimos 30 dias
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        
        new_groups = session.query(Group).filter(
            and_(
                Group.is_active == True,
                Group.created_at >= thirty_days_ago
            )
        ).order_by(Group.created_at.desc()).limit(5).all()
        
        if not new_groups:
            text = "🆕 **Grupos Novos**\n\n"
            text += "Nenhum grupo novo no momento."
        else:
            text = "🆕 **Grupos Novos**\n\n"
            text += "Confira os lançamentos mais recentes:\n\n"
            
            for group in new_groups:
                creator = group.creator
                days_active = (datetime.utcnow() - group.created_at).days
                
                # Buscar menor preço
                min_price = session.query(func.min(PricingPlan.price)).filter_by(
                    group_id=group.id,
                    is_active=True
                ).scalar()
                
                text += f"🌟 **{group.name}**\n"
                text += f"   👤 @{creator.username or creator.name}\n"
                text += f"   📅 Há {days_active} dias na plataforma\n"
                if min_price:
                    text += f"   💰 A partir de R$ {min_price:.2f}\n"
                text += "\n"
        
        keyboard = [[
            InlineKeyboardButton("⬅️ Voltar", callback_data="discover")
        ]]
        
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def show_cheapest_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostrar grupos mais baratos"""
    query = update.callback_query
    
    with get_db_session() as session:
        # Buscar grupos com planos mais baratos
        cheap_groups = []
        
        groups = session.query(Group).filter_by(is_active=True).all()
        
        for group in groups:
            min_price = session.query(func.min(PricingPlan.price)).filter_by(
                group_id=group.id,
                is_active=True
            ).scalar()
            
            if min_price and min_price <= 50:  # Barato = até R$ 50
                subscriber_count = session.query(Subscription).filter_by(
                    group_id=group.id,
                    status='active'
                ).count()
                
                cheap_groups.append({
                    'group': group,
                    'min_price': min_price,
                    'subscribers': subscriber_count
                })
        
        # Ordenar por preço
        cheap_groups.sort(key=lambda x: x['min_price'])
        cheap_groups = cheap_groups[:10]
        
        if not cheap_groups:
            text = "💰 **Grupos Mais em Conta**\n\n"
            text += "Nenhum grupo econômico disponível no momento."
        else:
            text = "💰 **Grupos Mais em Conta**\n\n"
            text += "Qualidade não precisa ser cara:\n\n"
            
            keyboard = []
            
            for data in cheap_groups:
                group = data['group']
                creator = group.creator
                
                text += f"✅ **{group.name}**\n"
                text += f"   👤 @{creator.username or creator.name}\n"
                text += f"   💵 Apenas R$ {data['min_price']:.2f}\n"
                text += f"   👥 {data['subscribers']} assinantes\n\n"
                
                # Adicionar botão
                keyboard.append([
                    InlineKeyboardButton(
                        f"Ver {group.name[:25]}...",
                        url=f"https://t.me/{context.bot.username}?start=g_{group.telegram_id}"
                    )
                ])
        
        keyboard.append([
            InlineKeyboardButton("⬅️ Voltar", callback_data="discover")
        ])
        
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def show_groups_by_category(update: Update, context: ContextTypes.DEFAULT_TYPE, category: str):
    """Mostrar grupos de uma categoria específica"""
    query = update.callback_query
    
    # Mapeamento de categorias (futuro: criar tabela no banco)
    category_names = {
        "trading": "Trading e Investimentos",
        "gaming": "Games e eSports",
        "education": "Educação e Cursos",
        "fitness": "Fitness e Saúde",
        "creative": "Arte e Criatividade",
        "tech": "Tecnologia",
        "music": "Música",
        "photo": "Fotografia",
        "food": "Culinária",
        "travel": "Viagens"
    }
    
    category_name = category_names.get(category, category.title())
    
    # Por enquanto, mostrar mensagem placeholder
    text = f"🏷️ **{category_name}**\n\n"
    text += "🚧 Sistema de categorias em desenvolvimento...\n\n"
    text += "Em breve você poderá filtrar grupos por categoria!"
    
    keyboard = [[
        InlineKeyboardButton("⬅️ Voltar", callback_data="categories")
    ]]
    
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )