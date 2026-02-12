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
    asyncio.create_task(audit_members_loop())

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
    """Verificar e processar assinaturas expiradas e suspensas (todas as categorias)"""
    try:
        with get_db_session() as session:
            now = datetime.utcnow()
            # Grace period for Stripe auto-renew subs (payment retry window)
            grace_cutoff = now - timedelta(days=3)

            # 1) Fetch ALL active subscriptions past their end_date
            all_expired = session.query(Subscription).filter(
                Subscription.status == 'active',
                Subscription.end_date < now
            ).all()

            # 2) Fetch suspended/disputed subscriptions — enforce removal
            suspended_subs = session.query(Subscription).filter(
                Subscription.status.in_(['suspended', 'disputed'])
            ).all()

            processed = 0
            skipped = 0

            # Process expired active subscriptions
            for sub in all_expired:
                is_stripe_managed = (
                    sub.stripe_subscription_id
                    and not sub.is_legacy
                )

                # For Stripe auto-renew subs, allow grace period for payment retry
                # Stripe may still process a renewal or fire webhook
                if (is_stripe_managed
                        and not sub.cancel_at_period_end
                        and sub.end_date > grace_cutoff):
                    skipped += 1
                    continue

                sub.status = 'expired'

                # Remover usuario do grupo
                await remove_from_group(sub)

                # Notificar usuario
                await notify_expiration(sub)

                sub_type = "legacy" if not is_stripe_managed else "stripe"
                logger.info(
                    f"Assinatura {sub.id} ({sub_type}) expirada - "
                    f"user {sub.telegram_user_id} removido do grupo {sub.group_id}"
                )
                processed += 1

            # Process suspended/disputed subscriptions — ensure user is removed
            suspended_processed = 0
            for sub in suspended_subs:
                await remove_from_group(sub)
                suspended_processed += 1
                logger.info(
                    f"Assinatura suspensa {sub.id} - "
                    f"user {sub.telegram_user_id} removido do grupo {sub.group_id}"
                )

            session.commit()

            if processed or skipped or suspended_processed:
                logger.info(
                    f"{processed} expiradas processadas, "
                    f"{skipped} stripe auto-renew aguardando grace period, "
                    f"{suspended_processed} suspensas re-verificadas"
                )
            else:
                logger.info("Nenhuma assinatura expirada ou suspensa")

    except Exception as e:
        logger.error(f"Erro ao verificar expiradas: {e}")


async def remove_from_group(subscription):
    """Remover usuario do grupo via Telegram Bot API (respeitando whitelist e admins)"""
    if not _application:
        logger.warning("Bot nao disponivel para remover usuario")
        return

    try:
        group = subscription.group
        if not group or not group.telegram_id:
            return

        user_id = int(subscription.telegram_user_id)
        chat_id = int(group.telegram_id)

        # Verificar se esta na whitelist
        if group.is_whitelisted(str(user_id)):
            logger.info(f"Usuario {user_id} na whitelist do grupo {chat_id} - nao removido")
            return

        # Verificar se é admin do grupo
        try:
            member_info = await _application.bot.get_chat_member(
                chat_id=chat_id,
                user_id=user_id
            )
            if member_info.status in ['administrator', 'creator']:
                logger.info(f"Usuario {user_id} e admin do grupo {chat_id} - nao removido")
                return
        except TelegramError:
            pass  # Se falhar, tenta remover normalmente

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
            f"Para renovar, clique abaixo:"
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


async def audit_members_loop():
    """Auditar membros dos grupos a cada 6 horas"""
    # Esperar bot estar pronto
    await asyncio.sleep(60)

    while True:
        try:
            logger.info("Iniciando auditoria de membros dos grupos...")
            await audit_group_members()
            await asyncio.sleep(21600)  # 6 horas
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Erro no audit_members_loop: {e}")
            await asyncio.sleep(3600)


async def audit_group_members():
    """Verificar se usuarios sem assinatura ativa ainda estao nos grupos"""
    if not _application:
        return

    try:
        with get_db_session() as session:
            # Get all groups with telegram_id
            groups = session.query(Group).filter(
                Group.telegram_id != None,
                Group.is_active == True
            ).all()

            total_removed = 0

            for group in groups:
                chat_id = int(group.telegram_id)

                # Get all non-active subscriptions for this group
                # (expired, cancelled, suspended) from last 30 days
                cutoff = datetime.utcnow() - timedelta(days=30)
                inactive_subs = session.query(Subscription).filter(
                    Subscription.group_id == group.id,
                    Subscription.status.in_(['expired', 'cancelled', 'suspended']),
                    Subscription.end_date >= cutoff
                ).all()

                # Get active user IDs for this group
                active_user_ids = set(
                    s.telegram_user_id for s in
                    session.query(Subscription).filter_by(
                        group_id=group.id,
                        status='active'
                    ).all()
                )

                # Build whitelist set for fast lookup
                whitelisted_ids = set(
                    e['telegram_id'] for e in group.get_whitelist()
                )

                for sub in inactive_subs:
                    # Skip if user has another active subscription for the same group
                    if sub.telegram_user_id in active_user_ids:
                        continue

                    # Skip if user is whitelisted
                    if sub.telegram_user_id in whitelisted_ids:
                        continue

                    user_id = int(sub.telegram_user_id)

                    try:
                        # Check if user is still in the group
                        member = await _application.bot.get_chat_member(
                            chat_id=chat_id,
                            user_id=user_id
                        )

                        # Skip admins and creators
                        if member.status in ['administrator', 'creator']:
                            continue

                        if member.status in ['member', 'restricted']:
                            # User is still in group without active subscription — remove
                            await _application.bot.ban_chat_member(
                                chat_id=chat_id,
                                user_id=user_id
                            )
                            await _application.bot.unban_chat_member(
                                chat_id=chat_id,
                                user_id=user_id,
                                only_if_banned=True
                            )
                            total_removed += 1
                            logger.info(
                                f"Audit: usuario {user_id} removido do grupo "
                                f"{group.name} (assinatura {sub.status})"
                            )

                    except TelegramError:
                        # User not in group or API error — skip
                        pass
                    except Exception as e:
                        logger.error(f"Audit error checking user {user_id} in group {chat_id}: {e}")

                    # Rate limiting: avoid hitting Telegram API too fast
                    await asyncio.sleep(0.5)

            logger.info(f"Auditoria concluida: {total_removed} usuarios removidos")

    except Exception as e:
        logger.error(f"Erro na auditoria de membros: {e}")


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
    """Enviar lembrete individual de renovacao - diferenciado por tipo"""
    if not _application:
        return

    try:
        group = subscription.group
        plan = subscription.plan
        user_id = int(subscription.telegram_user_id)

        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        from bot.utils.format_utils import format_remaining_text

        remaining = format_remaining_text(subscription.end_date)

        is_stripe_managed = (
            subscription.stripe_subscription_id
            and not getattr(subscription, 'is_legacy', False)
        )

        if is_stripe_managed and getattr(subscription, 'cancel_at_period_end', False):
            # User chose not to renew
            text = (
                f"⚠️ Sua assinatura do grupo **{group.name}** "
                f"encerra em **{remaining}**.\n\n"
                f"Voce optou por nao renovar. Apos essa data, voce perdera o acesso.\n\n"
                f"Mudou de ideia? Reative a renovacao automatica!"
            )
            keyboard = [[
                InlineKeyboardButton(
                    "🔄 Reativar Renovacao",
                    callback_data=f"reactivate_sub_{subscription.id}"
                )
            ]]
        elif is_stripe_managed and getattr(subscription, 'auto_renew', False):
            # Auto-renew active
            payment_type = getattr(subscription, 'payment_method_type', 'card')
            if payment_type == 'boleto':
                text = (
                    f"📋 Um novo boleto sera gerado em breve para renovacao "
                    f"do grupo **{group.name}**.\n\n"
                    f"Fique atento ao seu email para pagar o boleto a tempo!"
                )
            else:
                text = (
                    f"🔄 Sua assinatura do grupo **{group.name}** "
                    f"sera renovada automaticamente em **{remaining}**.\n\n"
                    f"Valor: R$ {plan.price:.2f}\n\n"
                    f"Nenhuma acao necessaria. O cartao cadastrado sera cobrado automaticamente."
                )
            keyboard = [[
                InlineKeyboardButton(
                    "📊 Ver Status",
                    callback_data="check_status"
                )
            ]]
        else:
            # Legacy subscription
            if days_left <= 1:
                urgency = "🔴 ULTIMO DIA"
            else:
                urgency = f"⚠️ {remaining} restantes"

            text = (
                f"{urgency}\n\n"
                f"Sua assinatura do grupo **{group.name}** "
                f"expira em **{remaining}**.\n\n"
                f"Plano: {plan.name} - R$ {plan.price:.2f}\n\n"
                f"Renove agora para nao perder o acesso!"
            )
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
