"""
Tarefas agendadas do bot - Controle de assinaturas
"""
import logging
import asyncio
from datetime import datetime, timedelta
from telegram.ext import Application
from telegram.error import TelegramError

from bot.utils.database import get_db_session
from app.models import Subscription, Group

logger = logging.getLogger(__name__)

# Referencia global para o bot
_application = None


def setup_jobs(application: Application):
    """Configurar jobs agendados"""
    global _application
    _application = application

    logger.info("Configurando sistema de tarefas agendadas...")

    asyncio.create_task(check_expired_loop())
    asyncio.create_task(send_reminders_loop())

    logger.info("Sistema de tarefas agendadas ativo")


async def check_expired_loop():
    """Verificar assinaturas expiradas a cada hora"""
    # Esperar bot estar pronto
    await asyncio.sleep(10)

    while True:
        try:
            logger.info("Verificando assinaturas expiradas...")
            await check_expired_subscriptions()
            await asyncio.sleep(3600)  # 1 hora
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Erro no check_expired_loop: {e}")
            await asyncio.sleep(60)


async def send_reminders_loop():
    """Enviar lembretes a cada 12 horas"""
    # Esperar bot estar pronto
    await asyncio.sleep(30)

    while True:
        try:
            logger.info("Enviando lembretes de renovacao...")
            await send_renewal_reminders()
            await asyncio.sleep(43200)  # 12 horas
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Erro no send_reminders_loop: {e}")
            await asyncio.sleep(3600)


async def check_expired_subscriptions():
    """Verificar e processar assinaturas expiradas"""
    try:
        with get_db_session() as session:
            expired = session.query(Subscription).filter(
                Subscription.status == 'active',
                Subscription.end_date < datetime.utcnow()
            ).all()

            if not expired:
                logger.info("Nenhuma assinatura expirada")
                return

            logger.info(f"Encontradas {len(expired)} assinaturas expiradas")

            for sub in expired:
                sub.status = 'expired'

                # Remover usuario do grupo
                await remove_from_group(sub)

                # Notificar usuario
                await notify_expiration(sub)

                logger.info(
                    f"Assinatura {sub.id} expirada - "
                    f"user {sub.telegram_user_id} removido do grupo {sub.group_id}"
                )

            session.commit()
            logger.info(f"{len(expired)} assinaturas processadas")

    except Exception as e:
        logger.error(f"Erro ao verificar expiradas: {e}")


async def remove_from_group(subscription):
    """Remover usuario do grupo via Telegram Bot API"""
    if not _application:
        logger.warning("Bot nao disponivel para remover usuario")
        return

    try:
        group = subscription.group
        if not group or not group.telegram_id:
            return

        user_id = int(subscription.telegram_user_id)
        chat_id = int(group.telegram_id)

        # Ban e unban = kick (remove sem banir permanentemente)
        await _application.bot.ban_chat_member(
            chat_id=chat_id,
            user_id=user_id
        )
        # Unban para permitir que volte se renovar
        await _application.bot.unban_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            only_if_banned=True
        )

        logger.info(f"Usuario {user_id} removido do grupo {chat_id}")

    except TelegramError as e:
        logger.error(f"Erro Telegram ao remover usuario: {e}")
    except Exception as e:
        logger.error(f"Erro ao remover do grupo: {e}")


async def notify_expiration(subscription):
    """Notificar usuario sobre expiracao"""
    if not _application:
        return

    try:
        group = subscription.group
        user_id = int(subscription.telegram_user_id)

        text = (
            f"⚠️ **Assinatura Expirada**\n\n"
            f"Sua assinatura do grupo **{group.name}** expirou.\n\n"
            f"Voce foi removido do grupo automaticamente.\n\n"
            f"Para renovar, use /descobrir ou clique abaixo:"
        )

        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        keyboard = [[
            InlineKeyboardButton(
                "🔄 Renovar Agora",
                callback_data=f"plan_{group.id}_{subscription.plan_id}"
            )
        ]]

        await _application.bot.send_message(
            chat_id=user_id,
            text=text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except TelegramError as e:
        # Usuario pode ter bloqueado o bot
        logger.warning(f"Nao foi possivel notificar usuario {subscription.telegram_user_id}: {e}")
    except Exception as e:
        logger.error(f"Erro ao notificar expiracao: {e}")


async def send_renewal_reminders():
    """Enviar lembretes de renovacao para assinaturas proximas de expirar"""
    if not _application:
        return

    try:
        with get_db_session() as session:
            reminders_sent = 0

            for days in [3, 1]:
                target_start = datetime.utcnow() + timedelta(days=days - 1)
                target_end = datetime.utcnow() + timedelta(days=days)

                subs = session.query(Subscription).filter(
                    Subscription.status == 'active',
                    Subscription.end_date >= target_start,
                    Subscription.end_date < target_end
                ).all()

                for sub in subs:
                    await send_renewal_notification(sub, days)
                    reminders_sent += 1

            logger.info(f"{reminders_sent} lembretes enviados")

    except Exception as e:
        logger.error(f"Erro ao enviar lembretes: {e}")


async def send_renewal_notification(subscription, days_left):
    """Enviar lembrete individual de renovacao"""
    if not _application:
        return

    try:
        group = subscription.group
        plan = subscription.plan
        user_id = int(subscription.telegram_user_id)

        if days_left == 1:
            urgency = "🔴 ULTIMO DIA"
        else:
            urgency = f"⚠️ {days_left} dias restantes"

        text = (
            f"{urgency}\n\n"
            f"Sua assinatura do grupo **{group.name}** "
            f"expira em **{days_left} dia(s)**.\n\n"
            f"Plano: {plan.name} - R$ {plan.price:.2f}\n\n"
            f"Renove agora para nao perder o acesso!"
        )

        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        keyboard = [[
            InlineKeyboardButton(
                "🔄 Renovar Agora",
                callback_data=f"plan_{group.id}_{plan.id}"
            )
        ]]

        await _application.bot.send_message(
            chat_id=user_id,
            text=text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except TelegramError:
        pass  # Usuario bloqueou o bot
    except Exception as e:
        logger.error(f"Erro ao enviar lembrete: {e}")
