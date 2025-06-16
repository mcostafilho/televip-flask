"""
Gerenciador automatizado de membros do grupo
"""
import logging
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import BadRequest
from telegram.constants import ParseMode

from bot.utils.database import get_db_session
from app.models import Subscription, Group

logger = logging.getLogger(__name__)

async def on_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Verificar se novo membro tem assinatura paga quando entra no grupo
    """
    if not update.message or not update.message.new_chat_members:
        return
        
    for member in update.message.new_chat_members:
        # Pular se for o próprio bot
        if member.id == context.bot.id:
            continue
        
        # Verificar se tem assinatura paga
        with get_db_session() as session:
            # Buscar grupo
            group = session.query(Group).filter_by(
                telegram_id=str(update.effective_chat.id)
            ).first()
            
            if not group:
                logger.warning(f"Grupo {update.effective_chat.id} não cadastrado no sistema")
                continue
            
            # Verificar assinatura
            subscription = session.query(Subscription).filter_by(
                group_id=group.id,
                telegram_user_id=str(member.id),
                status='active'
            ).first()
            
            if not subscription:
                # Não tem assinatura paga - remover!
                logger.info(f"❌ Usuário {member.id} tentou entrar sem assinatura em {group.name}")
                
                try:
                    # Remover do grupo
                    await context.bot.ban_chat_member(
                        chat_id=update.effective_chat.id,
                        user_id=member.id,
                        until_date=datetime.now() + timedelta(seconds=60)
                    )
                    
                    # Desbanir após 60 segundos (permite tentar novamente)
                    await asyncio.sleep(1)
                    await context.bot.unban_chat_member(
                        chat_id=update.effective_chat.id,
                        user_id=member.id
                    )
                    
                    # Avisar no privado se possível
                    try:
                        bot_username = context.bot.username
                        message = f"""
❌ **Acesso Negado!**

Você precisa ter uma assinatura ativa para entrar no grupo **{group.name}**.

💳 Para assinar, clique no botão abaixo:
"""
                        
                        keyboard = [[
                            InlineKeyboardButton(
                                "🔐 Assinar Grupo VIP",
                                url=f"https://t.me/{bot_username}?start=g_{group.telegram_id}"
                            )
                        ]]
                        
                        await context.bot.send_message(
                            chat_id=member.id,
                            text=message,
                            parse_mode=ParseMode.MARKDOWN,
                            reply_markup=InlineKeyboardMarkup(keyboard)
                        )
                    except:
                        # Usuário pode não ter iniciado conversa com o bot
                        pass
                    
                except Exception as e:
                    logger.error(f"Erro ao remover usuário: {e}")
            else:
                logger.info(f"✅ Usuário {member.username or member.id} tem assinatura válida para {group.name}")

async def remove_expired_members(context: ContextTypes.DEFAULT_TYPE):
    """
    Job para remover membros com assinatura expirada
    Executa a cada 6 horas
    """
    logger.info("🧹 Iniciando verificação de assinaturas expiradas...")
    
    with get_db_session() as session:
        # Buscar assinaturas que expiraram
        expired_subs = session.query(Subscription).filter(
            Subscription.status == 'active',
            Subscription.end_date < datetime.utcnow()
        ).all()
        
        logger.info(f"📋 Encontradas {len(expired_subs)} assinaturas expiradas")
        
        for sub in expired_subs:
            try:
                group = sub.group
                user_id = int(sub.telegram_user_id)
                
                # Tentar remover do grupo
                try:
                    await context.bot.ban_chat_member(
                        chat_id=group.telegram_id,
                        user_id=user_id,
                        until_date=datetime.now() + timedelta(seconds=30)
                    )
                    
                    # Desbanir logo em seguida (só remove, não bane permanente)
                    await asyncio.sleep(1)
                    await context.bot.unban_chat_member(
                        chat_id=group.telegram_id,
                        user_id=user_id
                    )
                    
                    logger.info(f"✅ Removido {sub.telegram_username} do grupo {group.name}")
                    
                except BadRequest as e:
                    if "user is not a member" in str(e).lower():
                        logger.info(f"Usuário {sub.telegram_username} já não está no grupo")
                    else:
                        logger.error(f"Erro ao remover usuário: {e}")
                
                # Atualizar status da assinatura
                sub.status = 'expired'
                
                # Decrementar contador de assinantes
                if group.total_subscribers > 0:
                    group.total_subscribers -= 1
                
                # Notificar usuário
                try:
                    bot_username = context.bot.username
                    message = f"""
❌ **Assinatura Expirada!**

Sua assinatura do grupo **{group.name}** expirou e você foi removido.

💳 Para renovar sua assinatura:
"""
                    
                    keyboard = [[
                        InlineKeyboardButton(
                            "🔄 Renovar Assinatura",
                            url=f"https://t.me/{bot_username}?start=g_{group.telegram_id}"
                        )
                    ]]
                    
                    await context.bot.send_message(
                        chat_id=sub.telegram_user_id,
                        text=message,
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                except:
                    logger.warning(f"Não foi possível notificar usuário {sub.telegram_user_id}")
                
                # Commit alterações
                session.commit()
                
                # Aguardar entre remoções para não sobrecarregar
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"Erro ao processar assinatura expirada: {e}")
                continue
    
    logger.info("✅ Verificação de assinaturas expiradas concluída")

async def send_renewal_reminders(context: ContextTypes.DEFAULT_TYPE):
    """
    Enviar lembretes para assinaturas próximas do vencimento
    Executa 1x por dia
    """
    logger.info("📨 Enviando lembretes de renovação...")
    
    with get_db_session() as session:
        # Buscar assinaturas que vencem em 3 dias
        three_days_later = datetime.utcnow() + timedelta(days=3)
        
        expiring_subs = session.query(Subscription).filter(
            Subscription.status == 'active',
            Subscription.end_date <= three_days_later,
            Subscription.end_date > datetime.utcnow()
        ).all()
        
        logger.info(f"📋 {len(expiring_subs)} assinaturas próximas do vencimento")
        
        for sub in expiring_subs:
            try:
                days_left = (sub.end_date - datetime.utcnow()).days
                group = sub.group
                bot_username = context.bot.username
                
                message = f"""
⏰ **Assinatura Expirando!**

Sua assinatura do grupo **{group.name}** vence em {days_left} dias!

💡 Renove agora e não perca o acesso ao conteúdo exclusivo.
"""
                
                keyboard = [[
                    InlineKeyboardButton(
                        "🔄 Renovar Agora",
                        url=f"https://t.me/{bot_username}?start=g_{group.telegram_id}"
                    )
                ]]
                
                await context.bot.send_message(
                    chat_id=sub.telegram_user_id,
                    text=message,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                
                logger.info(f"📨 Lembrete enviado para {sub.telegram_username}")
                
                # Aguardar entre envios
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Erro ao enviar lembrete: {e}")
                continue
    
    logger.info("✅ Lembretes de renovação enviados")