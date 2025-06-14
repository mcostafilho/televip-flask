# bot/handlers/admin.py
"""
Handler administrativo para criadores de conteúdo
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from datetime import datetime

from bot.utils.database import get_db_session
from app.models import Group, Creator, Subscription, Transaction

logger = logging.getLogger(__name__)

async def setup_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Configurar bot no grupo - comando /setup"""
    chat = update.effective_chat
    user = update.effective_user
    
    # Verificar se é um grupo
    if chat.type == 'private':
        await update.message.reply_text(
            "❌ Este comando deve ser usado dentro de um grupo!\n\n"
            "1. Adicione o bot ao seu grupo\n"
            "2. Promova o bot a administrador\n"
            "3. Use /setup dentro do grupo"
        )
        return
    
    # Verificar se o bot é admin
    bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
    if bot_member.status not in ['administrator', 'creator']:
        await update.message.reply_text(
            "❌ O bot precisa ser administrador do grupo!\n\n"
            "Por favor, promova o bot a administrador com estas permissões:\n"
            "✅ Adicionar novos membros\n"
            "✅ Remover membros\n"
            "✅ Gerenciar links de convite"
        )
        return
    
    # Verificar se o usuário é admin do grupo
    user_member = await context.bot.get_chat_member(chat.id, user.id)
    if user_member.status not in ['administrator', 'creator']:
        await update.message.reply_text(
            "❌ Apenas administradores do grupo podem usar este comando!"
        )
        return
    
    # Buscar se o grupo já está cadastrado
    with get_db_session() as session:
        existing_group = session.query(Group).filter_by(
            telegram_id=str(chat.id)
        ).first()
        
        if existing_group:
            creator = session.query(Creator).get(existing_group.creator_id)
            
            # Atualizar link de convite se não existir
            if not existing_group.invite_link:
                try:
                    invite_link = await context.bot.export_chat_invite_link(chat.id)
                    existing_group.invite_link = invite_link
                    session.commit()
                except:
                    pass
            
            message = f"""
✅ *Grupo já configurado!*

📱 *Nome:* {existing_group.name}
👤 *Criador:* {creator.name if creator else 'Desconhecido'}
🆔 *ID do Grupo:* `{chat.id}`
🔗 *Link do Bot:* https://t.me/{context.bot.username}?start=g_{chat.id}

Para gerenciar este grupo, acesse o painel web em:
https://televip.com/dashboard
"""
        else:
            # Gerar link de convite
            invite_link = None
            try:
                invite_link = await context.bot.export_chat_invite_link(chat.id)
            except:
                pass
            
            message = f"""
🎉 *Grupo pronto para configuração!*

🆔 *ID do Grupo:* `{chat.id}`
📱 *Nome do Grupo:* {chat.title}

*Próximos passos:*
1. Copie o ID acima
2. Acesse https://televip.com
3. Crie sua conta (se ainda não tiver)
4. Vá em "Criar Grupo"
5. Cole o ID do grupo no formulário

Após criar o grupo no painel, você receberá um link para compartilhar com seus seguidores!
"""
            
            if invite_link:
                message += f"\n🔗 *Link do Grupo:* {invite_link}"
    
    await update.message.reply_text(
        message,
        parse_mode=ParseMode.MARKDOWN
    )

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostrar estatísticas do grupo - comando /stats"""
    chat = update.effective_chat
    user = update.effective_user
    
    # Se for no privado, mostrar estatísticas gerais
    if chat.type == 'private':
        with get_db_session() as session:
            # Buscar criador pelo Telegram ID
            creator = session.query(Creator).filter_by(
                telegram_id=str(user.id)
            ).first()
            
            if not creator:
                await update.message.reply_text(
                    "❌ Você não está cadastrado como criador!\n\n"
                    "Acesse https://televip.com para criar sua conta."
                )
                return
            
            # Buscar grupos do criador
            groups = session.query(Group).filter_by(
                creator_id=creator.id
            ).all()
            
            if not groups:
                await update.message.reply_text(
                    "📊 Você ainda não tem grupos cadastrados.\n\n"
                    "Use /setup dentro de um grupo para começar!"
                )
                return
            
            # Calcular estatísticas
            total_subscribers = 0
            total_revenue = 0
            
            stats_text = "📊 *Suas Estatísticas Gerais*\n\n"
            
            for group in groups:
                active_subs = session.query(Subscription).filter_by(
                    group_id=group.id,
                    status='active'
                ).count()
                
                total_subscribers += active_subs
                
                # Receita do grupo
                group_revenue = session.query(
                    func.sum(Transaction.net_amount)
                ).join(Subscription).filter(
                    Subscription.group_id == group.id,
                    Transaction.status == 'completed'
                ).scalar() or 0
                
                total_revenue += group_revenue
                
                stats_text += f"📱 *{group.name}*\n"
                stats_text += f"   • Assinantes: {active_subs}\n"
                stats_text += f"   • Receita: R$ {group_revenue:.2f}\n\n"
            
            stats_text += f"\n💰 *Resumo:*\n"
            stats_text += f"• Total de Grupos: {len(groups)}\n"
            stats_text += f"• Total de Assinantes: {total_subscribers}\n"
            stats_text += f"• Receita Total: R$ {total_revenue:.2f}\n"
            stats_text += f"• Saldo Disponível: R$ {creator.balance:.2f}\n"
            
            await update.message.reply_text(
                stats_text,
                parse_mode=ParseMode.MARKDOWN
            )
    else:
        # Estatísticas do grupo específico
        # Verificar se usuário é admin
        user_member = await context.bot.get_chat_member(chat.id, user.id)
        if user_member.status not in ['administrator', 'creator']:
            await update.message.reply_text(
                "❌ Apenas administradores podem ver as estatísticas!"
            )
            return
        
        with get_db_session() as session:
            group = session.query(Group).filter_by(
                telegram_id=str(chat.id)
            ).first()
            
            if not group:
                await update.message.reply_text(
                    "❌ Grupo não configurado! Use /setup primeiro."
                )
                return
            
            # Estatísticas do grupo
            active_subs = session.query(Subscription).filter_by(
                group_id=group.id,
                status='active'
            ).count()
            
            total_subs = session.query(Subscription).filter_by(
                group_id=group.id
            ).count()
            
            # Receita do mês
            from datetime import timedelta
            month_ago = datetime.utcnow() - timedelta(days=30)
            
            monthly_revenue = session.query(
                func.sum(Transaction.net_amount)
            ).join(Subscription).filter(
                Subscription.group_id == group.id,
                Transaction.status == 'completed',
                Transaction.created_at >= month_ago
            ).scalar() or 0
            
            stats_text = f"""
📊 *Estatísticas - {group.name}*

👥 *Assinantes:*
• Ativos: {active_subs}
• Total: {total_subs}

💰 *Financeiro (últimos 30 dias):*
• Receita: R$ {monthly_revenue:.2f}
• Ticket Médio: R$ {(monthly_revenue / active_subs if active_subs > 0 else 0):.2f}

🔗 *Link de Assinatura:*
https://t.me/{context.bot.username}?start=g_{chat.id}
"""
            
            await update.message.reply_text(
                stats_text,
                parse_mode=ParseMode.MARKDOWN
            )

async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enviar mensagem para todos os assinantes - comando /broadcast"""
    user = update.effective_user
    
    # Verificar se é no privado
    if update.effective_chat.type != 'private':
        await update.message.reply_text(
            "❌ Use este comando no privado com o bot!"
        )
        return
    
    # Verificar se é um criador
    with get_db_session() as session:
        creator = session.query(Creator).filter_by(
            telegram_id=str(user.id)
        ).first()
        
        if not creator:
            await update.message.reply_text(
                "❌ Você não está cadastrado como criador!"
            )
            return
        
        # Verificar sintaxe
        if len(context.args) < 2:
            await update.message.reply_text(
                "📢 *Como usar o broadcast:*\n\n"
                "`/broadcast [ID_GRUPO] [MENSAGEM]`\n\n"
                "Exemplo:\n"
                "`/broadcast -1001234567890 Olá assinantes! Novo conteúdo disponível!`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        group_telegram_id = context.args[0]
        message = ' '.join(context.args[1:])
        
        # Buscar grupo
        group = session.query(Group).filter_by(
            telegram_id=group_telegram_id,
            creator_id=creator.id
        ).first()
        
        if not group:
            await update.message.reply_text(
                "❌ Grupo não encontrado ou você não é o dono!"
            )
            return
        
        # Buscar assinantes ativos
        subscribers = session.query(Subscription).filter_by(
            group_id=group.id,
            status='active'
        ).all()
        
        if not subscribers:
            await update.message.reply_text(
                "❌ Nenhum assinante ativo neste grupo."
            )
            return
        
        # Enviar mensagens
        sent = 0
        failed = 0
        
        broadcast_text = f"""
📢 *Mensagem do Criador - {group.name}*

{message}

_Esta é uma mensagem oficial do criador do grupo._
"""
        
        await update.message.reply_text(
            f"📤 Enviando para {len(subscribers)} assinantes..."
        )
        
        for sub in subscribers:
            try:
                await context.bot.send_message(
                    chat_id=sub.telegram_user_id,
                    text=broadcast_text,
                    parse_mode=ParseMode.MARKDOWN
                )
                sent += 1
            except:
                failed += 1
        
        await update.message.reply_text(
            f"✅ Broadcast concluído!\n\n"
            f"📤 Enviados: {sent}\n"
            f"❌ Falhas: {failed}"
        )