"""
Tarefas agendadas do bot - Controle de assinaturas
"""
import logging
import asyncio
import os
from datetime import datetime, timedelta
from telegram.ext import Application
from telegram.error import TelegramError
from telegram.constants import ParseMode

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
    asyncio.create_task(resubscribe_reminders_loop())

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
    """Verificar assinaturas expiradas: avisar → grace period 2 dias → remover"""
    try:
        with get_db_session() as session:
            now = datetime.utcnow()
            grace_days = 2
            grace_cutoff = now - timedelta(days=grace_days)
            stripe_grace_cutoff = now - timedelta(days=3)

            # ── Fase 1: Marcar como expiradas + avisar (NÃO remove ainda) ──
            newly_expired = session.query(Subscription).filter(
                Subscription.status == 'active',
                Subscription.end_date < now
            ).all()

            warned = 0
            skipped = 0
            for sub in newly_expired:
                is_stripe_managed = (
                    sub.stripe_subscription_id
                    and not sub.is_legacy
                )
                # Stripe auto-renew (não cancelado): grace period maior para retry
                if (is_stripe_managed
                        and not sub.cancel_at_period_end
                        and sub.end_date > stripe_grace_cutoff):
                    skipped += 1
                    continue

                sub.status = 'expired'
                await notify_expiration_warning(sub, grace_days)
                warned += 1
                logger.info(
                    f"Sub {sub.id} expirada - aviso enviado, "
                    f"remoção em {grace_days} dias"
                )

            # ── Fase 2: Remover do grupo após grace period de 2 dias ──
            to_remove = session.query(Subscription).filter(
                Subscription.status == 'expired',
                Subscription.end_date < grace_cutoff,
                Subscription.end_date > now - timedelta(days=30)
            ).all()

            removed = 0
            for sub in to_remove:
                # Pular se tem outra sub ativa para o mesmo grupo
                has_active = session.query(Subscription).filter(
                    Subscription.group_id == sub.group_id,
                    Subscription.telegram_user_id == sub.telegram_user_id,
                    Subscription.status == 'active',
                    Subscription.end_date > now
                ).first()
                if has_active:
                    continue

                was_removed = await remove_from_group(sub)
                if was_removed:
                    await notify_removal(sub)
                    removed += 1

            # ── Fase 3: Suspensos/disputados — remover sempre ──
            suspended_subs = session.query(Subscription).filter(
                Subscription.status.in_(['suspended', 'disputed'])
            ).all()
            suspended_processed = 0
            for sub in suspended_subs:
                await remove_from_group(sub)
                suspended_processed += 1

            session.commit()

            if warned or removed or skipped or suspended_processed:
                logger.info(
                    f"Expiradas: {warned} avisadas, {removed} removidas, "
                    f"{skipped} stripe aguardando, {suspended_processed} suspensas"
                )

    except Exception as e:
        logger.error(f"Erro ao verificar expiradas: {e}")


async def remove_from_group(subscription):
    """Remover usuario do grupo via Telegram Bot API (respeitando whitelist e admins).
    Returns True if user was actually removed, False otherwise."""
    if not _application:
        logger.warning("Bot nao disponivel para remover usuario")
        return False

    try:
        group = subscription.group
        if not group or not group.telegram_id:
            return False

        user_id = int(subscription.telegram_user_id)
        chat_id = int(group.telegram_id)

        # Verificar se esta na whitelist (criador) ou system whitelist (plataforma)
        if group.is_whitelisted(str(user_id)) or group.is_system_whitelisted(str(user_id)):
            logger.info(f"Usuario {user_id} na whitelist do grupo {chat_id} - nao removido")
            return False

        # Verificar status do membro no grupo
        try:
            member_info = await _application.bot.get_chat_member(
                chat_id=chat_id,
                user_id=user_id
            )
            if member_info.status in ['administrator', 'creator']:
                logger.info(f"Usuario {user_id} e admin do grupo {chat_id} - nao removido")
                return False
            if member_info.status in ['left', 'kicked']:
                # Já não está no grupo
                return False
        except TelegramError:
            return False  # Não conseguiu verificar — não remove

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
        return True

    except TelegramError as e:
        logger.error(f"Erro Telegram ao remover usuario: {e}")
        return False
    except Exception as e:
        logger.error(f"Erro ao remover do grupo: {e}")
        return False


async def notify_expiration_warning(subscription, grace_days=2):
    """Avisar usuario que assinatura expirou — tem X dias para renovar antes da remoção"""
    if not _application:
        return

    try:
        group = subscription.group
        user_id = int(subscription.telegram_user_id)

        from bot.utils.format_utils import escape_html
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        group_name = escape_html(group.name)
        type_label = "canal" if group.chat_type == 'channel' else "grupo"

        text = (
            f"<b>Assinatura expirada</b>\n\n"
            f"Sua assinatura de <b>{group_name}</b> expirou.\n\n"
            f"Você tem <b>{grace_days} dias</b> para renovar.\n"
            f"Após esse prazo, será removido do {type_label} automaticamente."
        )

        keyboard = [[
            InlineKeyboardButton(
                "Renovar Agora",
                callback_data=f"plan_{group.id}_{subscription.plan_id}"
            )
        ]]

        await _application.bot.send_message(
            chat_id=user_id,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except TelegramError:
        logger.warning(f"Nao foi possivel avisar usuario {subscription.telegram_user_id}")
    except Exception as e:
        logger.error(f"Erro ao notificar expiracao: {e}")


async def notify_removal(subscription):
    """Notificar usuario que foi removido do grupo após grace period"""
    if not _application:
        return

    try:
        group = subscription.group
        user_id = int(subscription.telegram_user_id)

        from bot.utils.format_utils import escape_html
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        group_name = escape_html(group.name)
        type_label = "canal" if group.chat_type == 'channel' else "grupo"

        text = (
            f"<b>Acesso removido</b>\n\n"
            f"Você foi removido do {type_label} <b>{group_name}</b> "
            f"por falta de renovação.\n\n"
            f"Para voltar, assine novamente."
        )

        keyboard = [[
            InlineKeyboardButton(
                "Assinar Novamente",
                callback_data=f"plan_{group.id}_{subscription.plan_id}"
            )
        ]]

        await _application.bot.send_message(
            chat_id=user_id,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except TelegramError:
        logger.warning(f"Nao foi possivel notificar remocao de {subscription.telegram_user_id}")
    except Exception as e:
        logger.error(f"Erro ao notificar remocao: {e}")


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

                # Build whitelist set for fast lookup (creator + system)
                whitelisted_ids = set(
                    e['telegram_id'] for e in group.get_whitelist()
                )
                whitelisted_ids.update(
                    e['telegram_id'] for e in group.get_system_whitelist()
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
        from bot.utils.format_utils import format_remaining_text, format_currency, escape_html

        remaining = format_remaining_text(subscription.end_date)
        group_name = escape_html(group.name)
        plan_name = escape_html(plan.name)

        is_stripe_managed = (
            subscription.stripe_subscription_id
            and not getattr(subscription, 'is_legacy', False)
        )

        if is_stripe_managed and getattr(subscription, 'cancel_at_period_end', False):
            # User chose not to renew
            text = (
                f"<b>Assinatura expirando</b>\n\n"
                f"Sua assinatura de <b>{group_name}</b> expira em <code>{remaining}</code>.\n"
                f"A renovação automática está desativada.\n\n"
                f"Reative para manter seu acesso."
            )
            keyboard = [[
                InlineKeyboardButton(
                    "Reativar",
                    callback_data=f"reactivate_sub_{subscription.id}"
                )
            ]]
        elif is_stripe_managed and getattr(subscription, 'auto_renew', False):
            # Auto-renew active — differentiate card vs boleto
            method = getattr(subscription, 'payment_method_type', 'card') or 'card'

            if method == 'boleto':
                text = (
                    f"<b>Renovação automática</b>\n\n"
                    f"Sua assinatura de <b>{group_name}</b> será renovada em <code>{remaining}</code>.\n"
                    f"Valor: <code>{format_currency(plan.price)}</code>\n\n"
                    f"<i>Um novo boleto será gerado automaticamente.\n"
                    f"Fique atento ao seu e-mail para o link de pagamento.</i>"
                )
            else:
                # Try to get card last4 and portal URL for better UX
                card_info = ""
                portal_url = None
                customer_id = getattr(subscription, 'stripe_customer_id', None)

                # Fetch card last4 from Stripe Subscription's default payment method
                if subscription.stripe_subscription_id:
                    try:
                        import stripe
                        stripe_sub = stripe.Subscription.retrieve(
                            subscription.stripe_subscription_id,
                            expand=['default_payment_method']
                        )
                        pm = stripe_sub.get('default_payment_method')
                        if pm and isinstance(pm, dict):
                            last4 = pm.get('card', {}).get('last4')
                            if last4:
                                card_info = f"\nCartão: <code>**** {last4}</code>"
                    except Exception as e:
                        logger.warning(f"Could not fetch card last4: {e}")

                # Generate a signed URL that creates a fresh portal session on click
                if customer_id:
                    try:
                        import jwt
                        base_url = os.getenv('BASE_URL', 'http://localhost:5000')
                        secret_key = os.getenv('SECRET_KEY', 'fallback-secret')
                        token = jwt.encode(
                            {
                                'customer_id': customer_id,
                                'purpose': 'billing_portal',
                                'exp': datetime.utcnow() + timedelta(hours=24),
                            },
                            secret_key,
                            algorithm='HS256'
                        )
                        portal_url = f"{base_url}/webhooks/billing-portal?t={token}"
                    except Exception as e:
                        logger.warning(f"Could not generate portal URL: {e}")

                text = (
                    f"<b>Renovação automática</b>\n\n"
                    f"Sua assinatura de <b>{group_name}</b> será renovada em <code>{remaining}</code>.\n"
                    f"Valor: <code>{format_currency(plan.price)}</code>"
                    f"{card_info}\n\n"
                    f"<i>A cobrança será feita automaticamente.</i>"
                )

                if portal_url:
                    keyboard = [[
                        InlineKeyboardButton(
                            "Gerenciar Pagamento",
                            url=portal_url
                        )
                    ]]
                else:
                    keyboard = [[
                        InlineKeyboardButton(
                            "Ver Status",
                            callback_data="check_status"
                        )
                    ]]
        else:
            # Legacy subscription
            text = (
                f"<b>Assinatura expirando</b>\n\n"
                f"Sua assinatura de <b>{group_name}</b> expira em <code>{remaining}</code>.\n\n"
                f"<pre>"
                f"Plano:    {plan.name}\n"
                f"Valor:    {format_currency(plan.price)}"
                f"</pre>\n\n"
                f"Renove agora para não perder o acesso."
            )
            keyboard = [[
                InlineKeyboardButton(
                    "Renovar Agora",
                    callback_data=f"plan_{group.id}_{plan.id}"
                )
            ]]

        await _application.bot.send_message(
            chat_id=user_id,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except TelegramError:
        pass  # Usuario bloqueou o bot
    except Exception as e:
        logger.error(f"Erro ao enviar lembrete: {e}")


# ──────────────────────────────────────────────
# Remarketing: lembretes para assinaturas expiradas
# ──────────────────────────────────────────────

async def resubscribe_reminders_loop():
    """Enviar lembretes de re-assinatura 1x por dia"""
    await asyncio.sleep(120)  # Esperar bot estar pronto

    while True:
        try:
            logger.info("Enviando lembretes de re-assinatura...")
            await send_resubscribe_reminders()
            await asyncio.sleep(86400)  # 24 horas
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Erro no resubscribe_reminders_loop: {e}")
            await asyncio.sleep(3600)


async def send_resubscribe_reminders():
    """Enviar lembretes para assinaturas expiradas (3, 14, 30 dias)"""
    if not _application:
        return

    try:
        with get_db_session() as session:
            now = datetime.utcnow()
            reminders_sent = 0

            # Janelas de lembrete: (dias desde expiração, tolerância em horas, tipo)
            windows = [
                (3, 24, 'soft'),
                (14, 24, 'incentive'),
                (30, 24, 'final'),
            ]

            for days, tolerance_hours, reminder_type in windows:
                target_start = now - timedelta(days=days, hours=tolerance_hours)
                target_end = now - timedelta(days=days) + timedelta(hours=tolerance_hours)

                expired_subs = session.query(Subscription).filter(
                    Subscription.status == 'expired',
                    Subscription.end_date >= target_start,
                    Subscription.end_date <= target_end
                ).all()

                for sub in expired_subs:
                    # Anti-spam: só envia se last_reminder_at é None ou > 7 dias atrás
                    if sub.last_reminder_at and (now - sub.last_reminder_at).days < 7:
                        continue

                    # Verificar se o grupo ainda está ativo
                    group = sub.group
                    if not group or not group.is_active:
                        continue

                    # Verificar se o usuário já tem outra sub ativa para este grupo
                    active_sub = session.query(Subscription).filter(
                        Subscription.group_id == group.id,
                        Subscription.telegram_user_id == sub.telegram_user_id,
                        Subscription.status == 'active',
                        Subscription.end_date > now
                    ).first()
                    if active_sub:
                        continue

                    sent = await _send_resubscribe_message(sub, reminder_type)
                    if sent:
                        sub.last_reminder_at = now
                        reminders_sent += 1

                session.commit()

            logger.info(f"Remarketing: {reminders_sent} lembretes de re-assinatura enviados")

    except Exception as e:
        logger.error(f"Erro no remarketing: {e}")


async def _send_resubscribe_message(subscription, reminder_type):
    """Enviar mensagem de remarketing individual"""
    if not _application:
        return False

    try:
        group = subscription.group
        user_id = int(subscription.telegram_user_id)

        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        from bot.utils.format_utils import escape_html

        group_name = escape_html(group.name)
        type_label = "canal" if group.chat_type == 'channel' else "grupo"
        bot_username = (await _application.bot.get_me()).username

        # Deep link para o grupo
        deep_link = f"https://t.me/{bot_username}?start=g_{group.invite_slug}"

        if reminder_type == 'soft':
            text = (
                f"Olá! Sua assinatura de <b>{group_name}</b> expirou há 3 dias.\n\n"
                f"Renove agora para continuar com acesso."
            )
        elif reminder_type == 'incentive':
            text = (
                f"Sentimos sua falta! Sua assinatura de <b>{group_name}</b> expirou.\n\n"
                f"Volte a fazer parte do {type_label}."
            )
        else:  # final
            text = (
                f"Último lembrete: sua assinatura de <b>{group_name}</b> expirou há 30 dias.\n\n"
                f"Não enviaremos mais lembretes sobre esta assinatura."
            )

        keyboard = [[
            InlineKeyboardButton("Assinar Novamente", url=deep_link)
        ]]

        await _application.bot.send_message(
            chat_id=user_id,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return True

    except TelegramError:
        return False  # Usuário bloqueou o bot
    except Exception as e:
        logger.error(f"Erro ao enviar remarketing para {subscription.telegram_user_id}: {e}")
        return False
