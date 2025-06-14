"""
Handler para gerenciar assinaturas
"""
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from bot.utils.database import get_db_session
from bot.keyboards.menus import get_renewal_keyboard
from app.models import Subscription, Group, PricingPlan

logger = logging.getLogger(__name__)

async def show_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostrar planos disponíveis do usuário"""
    user = update.effective_user
    
    with get_db_session() as session:
        # Buscar assinaturas do usuário
        subscriptions = session.query(Subscription).filter_by(
            telegram_user_id=str(user.id)
        ).all()
        
        if not subscriptions:
            await update.message.reply_text(
                "📭 Você ainda não tem nenhuma assinatura.\n\n"
                "Para assinar um grupo, use o link fornecido pelo criador."
            )
            return
        
        # Listar assinaturas
        message = "📋 *Suas Assinaturas:*\n\n"
        
        for sub in subscriptions:
            group = sub.group
            plan = sub.plan
            
            status_emoji = "✅" if sub.status == 'active' else "❌"
            
            message += f"{status_emoji} *{group.name}*\n"
            message += f"   • Plano: {plan.name}\n"
            message += f"   • Status: {sub.status}\n"
            message += f"   • Válido até: {sub.end_date.strftime('%d/%m/%Y')}\n"
            
            # Calcular dias restantes
            days_left = (sub.end_date - datetime.utcnow()).days
            if days_left > 0 and sub.status == 'active':
                message += f"   • Dias restantes: {days_left}\n"
            
            message += "\n"
        
        await update.message.reply_text(
            message,
            parse_mode=ParseMode.MARKDOWN
        )

async def check_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verificar status detalhado das assinaturas"""
    user = update.effective_user
    
    with get_db_session() as session:
        # Buscar assinaturas ativas
        active_subs = session.query(Subscription).filter_by(
            telegram_user_id=str(user.id),
            status='active'
        ).all()
        
        if not active_subs:
            await update.message.reply_text(
                "❌ Você não possui assinaturas ativas no momento.\n\n"
                "Use o link do criador para assinar um grupo."
            )
            return
        
        for sub in active_subs:
            group = sub.group
            plan = sub.plan
            days_left = (sub.end_date - datetime.utcnow()).days
            
            status_text = f"""
📊 *Status da Assinatura*

📱 *Grupo:* {group.name}
📋 *Plano:* {plan.name}
📅 *Início:* {sub.start_date.strftime('%d/%m/%Y')}
📅 *Término:* {sub.end_date.strftime('%d/%m/%Y')}
⏱️ *Dias restantes:* {days_left}

✅ *Status:* Ativa
"""
            
            # Se estiver próximo do vencimento, mostrar opção de renovar
            if days_left <= 7:
                status_text += "\n⚠️ *Sua assinatura está próxima do vencimento!*"
                keyboard = get_renewal_keyboard(sub.id)
                
                await update.message.reply_text(
                    status_text,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=keyboard
                )
            else:
                await update.message.reply_text(
                    status_text,
                    parse_mode=ParseMode.MARKDOWN
                )

async def handle_renewal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para renovação de assinatura"""
    query = update.callback_query
    await query.answer()
    
    # Extrair ID da assinatura
    sub_id = int(query.data.replace('renew_', ''))
    
    with get_db_session() as session:
        subscription = session.query(Subscription).get(sub_id)
        
        if not subscription:
            await query.edit_message_text("❌ Assinatura não encontrada.")
            return
        
        group = subscription.group
        plan = subscription.plan
        
        # Mostrar opções de renovação
        renewal_text = f"""
🔄 *Renovar Assinatura*

📱 *Grupo:* {group.name}
📋 *Plano atual:* {plan.name}
💰 *Valor:* R$ {plan.price:.2f}

Escolha uma opção de renovação:
"""
        
        # Criar botões com os planos disponíveis
        keyboard = []
        plans = group.pricing_plans.filter_by(is_active=True).all()
        
        for p in plans:
            keyboard.append([
                InlineKeyboardButton(
                    f"{p.name} - R$ {p.price:.2f}",
                    callback_data=f"plan_{group.id}_{p.id}"
                )
            ])
        
        keyboard.append([
            InlineKeyboardButton("❌ Cancelar", callback_data="cancel_renewal")
        ])
        
        await query.edit_message_text(
            renewal_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def send_renewal_reminder(bot, user_id: str, subscription_id: int):
    """Enviar lembrete de renovação"""
    with get_db_session() as session:
        subscription = session.query(Subscription).get(subscription_id)
        
        if not subscription:
            return
        
        group = subscription.group
        days_left = (subscription.end_date - datetime.utcnow()).days
        
        reminder_text = f"""
⏰ *Lembrete de Renovação*

Sua assinatura do grupo *{group.name}* vence em {days_left} dias!

💡 Renove agora para não perder o acesso ao conteúdo exclusivo.

Use /status para ver detalhes e renovar.
"""
        
        try:
            await bot.send_message(
                chat_id=user_id,
                text=reminder_text,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Erro ao enviar lembrete: {e}")

async def remove_expired_members(bot):
    """Remover membros com assinatura expirada"""
    with get_db_session() as session:
        # Buscar assinaturas expiradas
        expired_subs = session.query(Subscription).filter(
            Subscription.status == 'active',
            Subscription.end_date < datetime.utcnow()
        ).all()
        
        for sub in expired_subs:
            try:
                # Remover do grupo do Telegram
                # await bot.ban_chat_member(
                #     chat_id=sub.group.telegram_id,
                #     user_id=int(sub.telegram_user_id)
                # )
                
                # Atualizar status
                sub.status = 'expired'
                
                # Notificar usuário
                await bot.send_message(
                    chat_id=sub.telegram_user_id,
                    text=f"❌ Sua assinatura do grupo {sub.group.name} expirou.\n\n"
                         f"Para renovar, use /status"
                )
                
            except Exception as e:
                logger.error(f"Erro ao remover membro expirado: {e}")
        
        session.commit()