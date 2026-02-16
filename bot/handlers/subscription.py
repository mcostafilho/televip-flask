"""
Handler para gerenciamento de assinaturas
"""
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

import stripe
import os

from bot.utils.database import get_db_session
from bot.keyboards.menus import get_renewal_keyboard
from bot.utils.format_utils import (
    format_remaining_text, get_expiry_emoji, format_date, format_date_code,
    format_currency, format_currency_code, escape_html,
    is_sub_effectively_active, is_sub_renewing, try_fix_stale_end_date
)
from app import db
from app.models import Subscription, Group, Creator, PricingPlan, Transaction
from app.services.payment_service import PaymentService

stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

logger = logging.getLogger(__name__)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostrar status detalhado de todas as assinaturas"""
    # Detectar se é comando ou callback
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        user = query.from_user
        message = query.message
    else:
        user = update.effective_user
        message = update.message

    with get_db_session() as session:
        # Buscar TODAS as assinaturas do usuário
        all_subs = session.query(Subscription).filter_by(
            telegram_user_id=str(user.id)
        ).order_by(
            Subscription.status.desc(),  # Ativas primeiro
            Subscription.end_date.desc()  # Mais recentes primeiro
        ).all()

        if not all_subs:
            text = "Você ainda não possui nenhuma assinatura.\n\nPara assinar um grupo, use o link de convite fornecido pelo criador."

            await message.reply_text(text, parse_mode=ParseMode.HTML)
            return

        # Auto-corrigir subs Stripe expiradas incorretamente ANTES de categorizar
        now = datetime.utcnow()
        for s in all_subs:
            if s.status == 'expired' and s.stripe_subscription_id and not s.is_legacy:
                if s.end_date and s.end_date <= now:
                    try_fix_stale_end_date(s)

        # Separar por status (após correção)
        active = [s for s in all_subs if s.status == 'active']
        active_group_ids = {s.group_id for s in active}
        expired = [s for s in all_subs if s.status == 'expired' and s.group_id not in active_group_ids]
        cancelled = [s for s in all_subs if s.status == 'cancelled']

        # Calcular estatísticas
        total_spent = sum(t.amount for s in all_subs for t in s.transactions if t.status == 'completed')

        text = "<b>Suas assinaturas</b>\n\n"

        text += (
            f"<pre>"
            f"Assinaturas ativas:  {len(active)}\n"
            f"Total investido:     {format_currency(total_spent)}"
            f"</pre>\n"
        )

        # Listar ativas detalhadamente
        need_renewal_urgent = []
        need_renewal_soon = []

        if active:
            for sub in active:
                group = sub.group
                plan = sub.plan
                is_lifetime = getattr(plan, 'is_lifetime', False) or plan.duration_days == 0
                group_name = escape_html(group.name)
                plan_name = escape_html(plan.name)

                now = datetime.utcnow()

                # Corrigir end_date defasado (webhook pode ter falhado antes)
                if sub.end_date and sub.end_date <= now:
                    try_fix_stale_end_date(sub)

                renewing = is_sub_renewing(sub, now)

                if is_lifetime:
                    emoji = "♾️"
                elif renewing:
                    emoji = "🔄"
                    remaining = "Renovando..."
                else:
                    remaining = format_remaining_text(sub.end_date)
                    emoji = get_expiry_emoji(sub.end_date)
                    days_left = (sub.end_date - now).days

                    # Classificar urgência
                    if days_left <= 3:
                        need_renewal_urgent.append(sub)
                    elif days_left <= 7:
                        need_renewal_soon.append(sub)

                text += f"\n{emoji} <b>{group_name}</b>\n"
                text += f"   Plano: <code>{plan_name}</code>\n"

                if is_lifetime:
                    text += f"   Acesso vitalício\n"
                elif renewing:
                    text += f"   Status: Renovando...\n"
                else:
                    text += f"   Expira: {format_date_code(sub.end_date)} ({remaining})\n"

                    # Subscription status info
                    if getattr(sub, 'cancel_at_period_end', False):
                        text += f"   Renovação: cancelada\n"
                    elif getattr(sub, 'auto_renew', False) and sub.stripe_subscription_id and not getattr(sub, 'is_legacy', False):
                        text += f"   Renovação: automática\n"
                    elif getattr(sub, 'is_legacy', False) or not sub.stripe_subscription_id:
                        text += f"   Renovação: manual\n"

        # Listar expiradas recentes
        if expired:
            recent_expired = expired[:3]
            text += "\n<i>Expiradas:"
            for sub in recent_expired:
                group_name = escape_html(sub.group.name)
                text += f" {group_name},"
            text = text.rstrip(",") + "</i>\n"

        # Criar botões baseados no contexto
        keyboard = []

        # Botões de ação para cada assinatura ativa
        for sub in active:
            group = sub.group
            group_name_short = group.name[:15]
            row = [
                InlineKeyboardButton(
                    f"Link: {group_name_short}",
                    callback_data=f"get_link_{sub.id}"
                )
            ]
            if getattr(sub, 'cancel_at_period_end', False):
                row.append(
                    InlineKeyboardButton(
                        "Reativar",
                        callback_data=f"reactivate_sub_{sub.id}"
                    )
                )
            else:
                row.append(
                    InlineKeyboardButton(
                        "Cancelar",
                        callback_data=f"cancel_sub_{sub.id}"
                    )
                )
            keyboard.append(row)

        # Botão voltar
        keyboard.append([
            InlineKeyboardButton("Menu Principal", callback_data="back_to_start")
        ])

        # Responder
        if update.callback_query:
            await query.edit_message_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await message.reply_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

async def planos_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Listar todos os planos ativos do usuário"""
    user = update.effective_user

    with get_db_session() as session:
        # Buscar apenas assinaturas ativas
        active_subs = session.query(Subscription).filter_by(
            telegram_user_id=str(user.id),
            status='active'
        ).order_by(Subscription.end_date).all()

        if not active_subs:
            text = "Você não possui planos ativos no momento.\n\nPara assinar um grupo, use o link de convite fornecido pelo criador."
            keyboard = []
        else:
            text = f"<b>Seus {len(active_subs)} planos ativos</b>\n"

            for sub in active_subs:
                group = sub.group
                plan = sub.plan
                is_lifetime = getattr(plan, 'is_lifetime', False) or plan.duration_days == 0
                group_name = escape_html(group.name)
                plan_name = escape_html(plan.name)

                text += f"\n<b>{group_name}</b>\n"
                text += f"   Plano: <code>{plan_name}</code> — {format_currency(plan.price)}\n"

                if is_lifetime:
                    text += f"   Acesso vitalício\n"
                else:
                    remaining = format_remaining_text(sub.end_date)
                    text += f"   Expira em: {remaining} ({format_date_code(sub.end_date)})\n"

            keyboard = [
                [InlineKeyboardButton("Ver Detalhes", callback_data="check_status")]
            ]

        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def handle_renewal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processar renovação de assinatura"""
    query = update.callback_query
    await query.answer()

    # Identificar tipo de renovação
    if query.data == "check_renewals":
        await show_renewals_list(update, context)
    elif query.data == "renew_urgent":
        await show_urgent_renewals(update, context)
    elif query.data == "renew_soon":
        await show_soon_renewals(update, context)
    elif query.data.startswith("renew_"):
        # Renovar assinatura específica
        sub_id = int(query.data.replace("renew_", ""))
        await process_renewal(update, context, sub_id)

async def show_renewals_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostrar lista de assinaturas para renovar"""
    query = update.callback_query
    user = query.from_user

    with get_db_session() as session:
        # Buscar assinaturas que expiram em até 15 dias
        expiring = session.query(Subscription).filter(
            Subscription.telegram_user_id == str(user.id),
            Subscription.status == 'active',
            Subscription.end_date <= datetime.utcnow() + timedelta(days=15)
        ).order_by(Subscription.end_date).all()

        if not expiring:
            text = (
                "<b>Renovações</b>\n\n"
                "Todas as suas assinaturas estão em dia.\n"
                "Nenhuma renovação necessária nos próximos 15 dias."
            )
            keyboard = [[
                InlineKeyboardButton("Voltar", callback_data="check_status")
            ]]
        else:
            text = "<b>Renovações pendentes</b>\n"

            keyboard = []

            for sub in expiring:
                group = sub.group
                plan = sub.plan
                remaining = format_remaining_text(sub.end_date)
                emoji = get_expiry_emoji(sub.end_date)
                group_name = escape_html(group.name)
                plan_name = escape_html(plan.name)

                text += (
                    f"\n{emoji} <b>{group_name}</b>\n"
                    f"   Expira em: <code>{remaining}</code>\n"
                    f"   Plano: <code>{plan_name}</code> — {format_currency(plan.price)}\n"
                )

                # Botão para renovar
                keyboard.append([
                    InlineKeyboardButton(
                        f"Renovar {group.name[:20]} ({format_currency(plan.price)})",
                        callback_data=f"renew_{sub.id}"
                    )
                ])

            keyboard.append([
                InlineKeyboardButton("Voltar", callback_data="check_status")
            ])

        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def show_urgent_renewals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostrar apenas renovações urgentes (3 dias ou menos)"""
    query = update.callback_query
    user = query.from_user

    with get_db_session() as session:
        urgent = session.query(Subscription).filter(
            Subscription.telegram_user_id == str(user.id),
            Subscription.status == 'active',
            Subscription.end_date <= datetime.utcnow() + timedelta(days=3)
        ).order_by(Subscription.end_date).all()

        text = "<b>Renovações urgentes</b>\n\n"

        keyboard = []

        for sub in urgent:
            group = sub.group
            plan = sub.plan
            remaining = format_remaining_text(sub.end_date)
            group_name = escape_html(group.name)

            text += (
                f"<b>{group_name}</b>\n"
                f"   Expira em: <code>{remaining}</code>\n"
                f"   Renovar por: {format_currency(plan.price)}\n\n"
            )

            keyboard.append([
                InlineKeyboardButton(
                    f"Renovar {group.name[:25]}",
                    callback_data=f"renew_{sub.id}"
                )
            ])

        keyboard.append([
            InlineKeyboardButton("Voltar", callback_data="check_status")
        ])

        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def process_renewal(update: Update, context: ContextTypes.DEFAULT_TYPE, sub_id: int):
    """Processar renovação — reutiliza fluxo de pagamento existente (pay_stripe/pay_pix)."""
    from bot.handlers.payment import _cancel_pending, _order_summary_text

    query = update.callback_query

    with get_db_session() as session:
        sub = session.query(Subscription).get(sub_id)

        if not sub:
            await query.edit_message_text("Assinatura não encontrada.")
            return

        group = sub.group
        plan = sub.plan
        if not group or not plan:
            await query.edit_message_text("Grupo ou plano não encontrado.")
            return

        now = datetime.utcnow()
        still_active = is_sub_effectively_active(sub, now)
        amount = float(plan.price)

        # Calculate fees using bot's session (same logic as start_payment)
        from bot.handlers.payment import _get_fee_rates
        creator = group.creator
        if creator:
            fees = _get_fee_rates(session, creator, group)
            fee_result = PaymentService.calculate_fees(
                amount,
                fixed_fee=fees['fixed_fee'] if fees['is_custom'] else None,
                percentage_fee=fees['percentage_fee'] if fees['is_custom'] else None
            )
            platform_fee = float(fee_result['total_fee'])
            creator_amount = float(fee_result['net_amount'])
        else:
            fee_result = PaymentService.calculate_fees(amount)
            platform_fee = float(fee_result['total_fee'])
            creator_amount = float(fee_result['net_amount'])

        checkout_data = {
            'group_id': group.id,
            'plan_id': plan.id,
            'amount': amount,
            'platform_fee': platform_fee,
            'creator_amount': creator_amount,
            'duration_days': plan.duration_days,
            'is_lifetime': False,
            'group_name': group.name,
            'plan_name': plan.name,
            'is_renewal': True,
        }

        if still_active:
            # Sub ainda ativa: cobrança futura, só cartão
            checkout_data['trial_end'] = int(sub.end_date.timestamp())
            checkout_data['existing_sub_id'] = sub.id

        # Limpar pendentes anteriores e salvar checkout
        _cancel_pending(context)
        context.user_data['checkout'] = checkout_data

        text = _order_summary_text(checkout_data)

        if still_active:
            text += "\n\n<i>Confirme com seu cartão:</i>"
            keyboard = [
                [InlineKeyboardButton("💳 Confirmar com Cartão", callback_data="pay_stripe")],
                [InlineKeyboardButton("↩ Voltar", callback_data=f"sub_detail_{sub.id}")]
            ]
        else:
            short_plan = plan.duration_days and plan.duration_days <= 4
            text += "\n\n<i>Escolha a forma de pagamento:</i>"
            if short_plan:
                checkout_data['no_boleto'] = True
                keyboard = [
                    [InlineKeyboardButton("💳 Cartão", callback_data="pay_stripe")],
                    [InlineKeyboardButton("⚡ PIX", callback_data="pay_pix")],
                    [InlineKeyboardButton("↩ Voltar", callback_data=f"sub_detail_{sub.id}")]
                ]
            else:
                keyboard = [
                    [InlineKeyboardButton("💳 Cartão / Boleto", callback_data="pay_stripe")],
                    [InlineKeyboardButton("⚡ PIX", callback_data="pay_pix")],
                    [InlineKeyboardButton("↩ Voltar", callback_data=f"sub_detail_{sub.id}")]
                ]

        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def cancel_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostrar confirmação de cancelamento de assinatura"""
    query = update.callback_query
    await query.answer()
    user = query.from_user

    # Extrair sub_id do callback_data "cancel_sub_123"
    sub_id = int(query.data.replace("cancel_sub_", ""))

    with get_db_session() as session:
        sub = session.query(Subscription).get(sub_id)

        if not sub or sub.telegram_user_id != str(user.id) or sub.status != 'active':
            await query.edit_message_text("Assinatura não encontrada ou já cancelada.")
            return

        group = sub.group
        group_name = escape_html(group.name)

        # Differentiate Stripe-managed vs legacy
        if sub.stripe_subscription_id and not sub.is_legacy:
            cancel_text = (
                f"A renovação automática será desativada.\n"
                f"Você mantém acesso até {format_date_code(sub.end_date)}."
            )
        else:
            cancel_text = (
                f"Sua assinatura não será renovada.\n"
                f"Acesso até {format_date_code(sub.end_date)}."
            )

        text = (
            f"<b>Cancelar assinatura?</b>\n\n"
            f"Grupo: <b>{group_name}</b>\n\n"
            f"{cancel_text}"
        )

        keyboard = [
            [
                InlineKeyboardButton("Sim, cancelar", callback_data=f"confirm_cancel_sub_{sub.id}"),
                InlineKeyboardButton("Manter", callback_data="back_to_start")
            ]
        ]

        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def confirm_cancel_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirmar cancelamento — Stripe cancel_at_period_end ou legacy immediate"""
    query = update.callback_query
    await query.answer()
    user = query.from_user

    sub_id = int(query.data.replace("confirm_cancel_sub_", ""))

    with get_db_session() as session:
        sub = session.query(Subscription).get(sub_id)

        if not sub or sub.telegram_user_id != str(user.id) or sub.status != 'active':
            await query.edit_message_text("Assinatura não encontrada ou já cancelada.")
            return

        group_name = escape_html(sub.group.name)
        end_date_str = format_date(sub.end_date) if sub.end_date else 'N/A'

        if sub.stripe_subscription_id and not sub.is_legacy:
            # Stripe-managed: cancel at period end (keep access until end_date)
            try:
                stripe.Subscription.modify(
                    sub.stripe_subscription_id,
                    cancel_at_period_end=True
                )
                sub.cancel_at_period_end = True
                sub.auto_renew = False
                session.commit()

                text = (
                    f"<b>Cancelamento confirmado</b>\n\n"
                    f"Sua assinatura de <b>{group_name}</b> não será renovada.\n"
                    f"Você mantém acesso até {format_date_code(sub.end_date)}."
                )

                keyboard = [
                    [InlineKeyboardButton("Reativar", callback_data=f"reactivate_sub_{sub.id}")],
                    [InlineKeyboardButton("Menu Principal", callback_data="back_to_start")]
                ]

            except stripe.error.StripeError as e:
                logger.error(f"Stripe error cancelling subscription: {e}")
                text = (
                    "Erro ao cancelar assinatura no Stripe.\n"
                    "Tente novamente ou entre em contato com o suporte."
                )
                keyboard = [[InlineKeyboardButton("Menu", callback_data="back_to_start")]]
        else:
            # Legacy: cancel at period end (manter acesso até expirar)
            sub.cancel_at_period_end = True
            sub.auto_renew = False
            session.commit()

            text = (
                f"<b>Cancelamento confirmado</b>\n\n"
                f"Sua assinatura de <b>{group_name}</b> não será renovada.\n"
                f"Você mantém acesso até {format_date_code(sub.end_date)}."
            )

            keyboard = [[InlineKeyboardButton("Menu Principal", callback_data="back_to_start")]]

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def reactivate_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reactivate a subscription that was set to cancel at period end"""
    query = update.callback_query
    await query.answer()
    user = query.from_user

    sub_id = int(query.data.replace("reactivate_sub_", ""))

    with get_db_session() as session:
        sub = session.query(Subscription).get(sub_id)

        if not sub or sub.telegram_user_id != str(user.id):
            await query.edit_message_text("Assinatura não encontrada.")
            return

        if not sub.stripe_subscription_id or not sub.cancel_at_period_end:
            await query.edit_message_text("Esta assinatura não pode ser reativada.")
            return

        try:
            stripe.Subscription.modify(
                sub.stripe_subscription_id,
                cancel_at_period_end=False
            )
            sub.cancel_at_period_end = False
            sub.auto_renew = True
            session.commit()

            group_name = escape_html(sub.group.name)

            text = (
                f"<b>Renovação reativada</b>\n\n"
                f"A renovação automática de <b>{group_name}</b> foi reativada."
            )

            keyboard = [[InlineKeyboardButton("Menu Principal", callback_data="back_to_start")]]

        except stripe.error.StripeError as e:
            logger.error(f"Stripe error reactivating subscription: {e}")
            text = "Erro ao reativar. Tente novamente."
            keyboard = [[InlineKeyboardButton("Menu", callback_data="back_to_start")]]

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def get_invite_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gerar novo link de convite para assinatura ativa"""
    query = update.callback_query
    await query.answer("Gerando link...")
    user = query.from_user

    sub_id = int(query.data.replace("get_link_", ""))

    with get_db_session() as session:
        sub = session.query(Subscription).get(sub_id)

        if not sub or sub.telegram_user_id != str(user.id) or sub.status != 'active':
            await query.edit_message_text(
                "Assinatura não encontrada ou inativa.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("Menu", callback_data="back_to_start")
                ]])
            )
            return

        group = sub.group
        if not group or not group.telegram_id:
            await query.edit_message_text(
                "Grupo sem Telegram ID configurado. Contacte o suporte.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("Menu", callback_data="back_to_start")
                ]])
            )
            return

        group_name = escape_html(group.name)
        type_label = "canal" if group.chat_type == 'channel' else "grupo"

        try:
            link_obj = await context.bot.create_chat_invite_link(
                chat_id=int(group.telegram_id),
                member_limit=1,
                expire_date=datetime.utcnow() + timedelta(days=7),
                creates_join_request=False
            )
            invite_link = link_obj.invite_link

            text = (
                f"<b>Link de acesso</b>\n\n"
                f"Use o botão abaixo para entrar no {type_label} <b>{group_name}</b>.\n\n"
                f"<i>O link é de uso único e expira em 7 dias.</i>"
            )

            keyboard = [
                [InlineKeyboardButton(f"Entrar no {type_label.capitalize()}", url=invite_link)],
                [InlineKeyboardButton("↩ Voltar", callback_data="subs_active")]
            ]

        except Exception as e:
            error_str = str(e).lower()
            logger.error(f"Erro ao gerar invite link: {e}")

            if 'not enough rights' in error_str or 'chat_admin_required' in error_str:
                text = (
                    f"<b>Sem permissão</b>\n\n"
                    f"O bot não tem permissão de administrador no {type_label} <b>{group_name}</b>.\n"
                    f"O criador precisa verificar as configurações."
                )
            elif 'chat not found' in error_str or 'chat_not_found' in error_str:
                text = (
                    f"<b>{type_label.capitalize()} indisponível</b>\n\n"
                    f"O {type_label} <b>{group_name}</b> não foi encontrado.\n"
                    f"Pode ter sido removido ou o bot foi desconectado."
                )
            elif 'too many requests' in error_str or 'retry_after' in error_str:
                text = (
                    f"<b>Muitas tentativas</b>\n\n"
                    f"Aguarde alguns segundos e tente novamente."
                )
            else:
                text = (
                    f"Não foi possível gerar o link para <b>{group_name}</b>.\n\n"
                    f"Tente novamente em alguns instantes."
                )

            keyboard = [
                [InlineKeyboardButton("🔄 Tentar Novamente", callback_data=f"get_link_{sub.id}")],
                [InlineKeyboardButton("↩ Voltar", callback_data="subs_active")]
            ]

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

SUBS_PER_PAGE = 5


def _renewal_text(sub):
    """Texto de renovação baseado no tipo de assinatura"""
    if getattr(sub, 'cancel_at_period_end', False):
        return "Cancelada"
    if getattr(sub, 'auto_renew', False) and sub.stripe_subscription_id and not getattr(sub, 'is_legacy', False):
        return "Automática"
    return "Manual"


def _billing_reason_text(reason):
    """Texto legível para billing_reason"""
    mapping = {
        'subscription_create': 'Assinatura inicial',
        'subscription_cycle': 'Renovação',
        'lifetime_purchase': 'Compra vitalícia',
        'plan_change': 'Troca de plano',
    }
    return mapping.get(reason, reason or 'Pagamento')


# ──────────────────────────────────────────────
# Fase 3: Minhas Assinaturas (ativas)
# ──────────────────────────────────────────────

async def show_active_subscriptions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Listar assinaturas ativas com paginação — callback subs_active / subs_active_p{page}"""
    query = update.callback_query
    await query.answer()
    user = query.from_user

    # Extrair página
    page = 0
    data = query.data
    if '_p' in data:
        try:
            page = int(data.split('_p')[1])
        except (IndexError, ValueError):
            page = 0

    now = datetime.utcnow()

    with get_db_session() as session:
        all_active = session.query(Subscription).filter(
            Subscription.telegram_user_id == str(user.id),
            Subscription.status == 'active',
            Subscription.end_date > now - timedelta(hours=2)
        ).order_by(Subscription.end_date).all()

        if not all_active:
            text = (
                "✅ <b>Minhas Assinaturas</b>\n\n"
                "Você não possui assinaturas ativas."
            )
            keyboard = [[InlineKeyboardButton("↩ Voltar", callback_data="back_to_start")]]
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
            return

        total = len(all_active)
        start = page * SUBS_PER_PAGE
        page_subs = all_active[start:start + SUBS_PER_PAGE]

        text = "✅ <b>Assinaturas Ativas</b>\n"

        for sub in page_subs:
            group = sub.group
            plan = sub.plan
            group_name = escape_html(group.name) if group else "N/A"
            plan_name = escape_html(plan.name) if plan else "N/A"
            is_lifetime = getattr(plan, 'is_lifetime', False) or (plan and plan.duration_days == 0)

            if is_lifetime:
                emoji = "♾️"
                remaining = "Vitalício"
            elif is_sub_renewing(sub, now):
                emoji = "🔄"
                remaining = "Renovando..."
            else:
                emoji = get_expiry_emoji(sub.end_date)
                remaining = format_remaining_text(sub.end_date)

            renewal = _renewal_text(sub)

            text += (
                f"\n{emoji} <b>{group_name}</b>\n"
                f"   {plan_name} · {remaining}\n"
                f"   Renovação: {renewal}\n"
            )

        # Botões: 1 por sub para detalhe
        keyboard = []
        for sub in page_subs:
            group_name_short = sub.group.name[:25] if sub.group else "N/A"
            keyboard.append([
                InlineKeyboardButton(group_name_short, callback_data=f"sub_detail_{sub.id}")
            ])

        # Paginação
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("⬅️", callback_data=f"subs_active_p{page - 1}"))
        if start + SUBS_PER_PAGE < total:
            nav_row.append(InlineKeyboardButton("➡️", callback_data=f"subs_active_p{page + 1}"))
        if nav_row:
            keyboard.append(nav_row)

        keyboard.append([InlineKeyboardButton("↩ Voltar", callback_data="back_to_start")])

        await query.edit_message_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


# ──────────────────────────────────────────────
# Fase 4: Detalhe da Assinatura
# ──────────────────────────────────────────────

async def show_subscription_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostrar detalhe de uma assinatura — callback sub_detail_{id}"""
    query = update.callback_query
    await query.answer()
    user = query.from_user

    sub_id = int(query.data.replace("sub_detail_", ""))

    with get_db_session() as session:
        sub = session.query(Subscription).get(sub_id)

        if not sub or sub.telegram_user_id != str(user.id):
            await query.edit_message_text(
                "Assinatura não encontrada.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("Menu", callback_data="back_to_start")
                ]])
            )
            return

        group = sub.group
        plan = sub.plan
        group_name = escape_html(group.name) if group else "N/A"
        plan_name = escape_html(plan.name) if plan else "N/A"
        type_label = "canal" if (group and group.chat_type == 'channel') else "grupo"
        is_lifetime = getattr(plan, 'is_lifetime', False) or (plan and plan.duration_days == 0)
        now = datetime.utcnow()
        is_active = is_sub_effectively_active(sub, now)
        renewing = is_sub_renewing(sub, now)

        # Status text
        if renewing:
            emoji = "🔄"
            status_text = "Renovando..."
        elif is_active:
            if is_lifetime:
                emoji = "♾️"
                status_text = "Ativo (vitalício)"
            else:
                emoji = get_expiry_emoji(sub.end_date)
                status_text = "Ativo"
        elif sub.status == 'cancelled':
            emoji = "🚫"
            status_text = "Cancelada"
        else:
            emoji = "❌"
            status_text = "Expirada"

        renewal = _renewal_text(sub) if is_active and not is_lifetime else "—"

        cycle_text = "Vitalício" if is_lifetime else f"{plan.duration_days} dias" if plan else "N/A"
        text = (
            f"{emoji} <b>{group_name}</b>\n"
            f"{type_label.capitalize()}\n\n"
            f"<pre>"
            f"Plano:      {plan_name}\n"
            f"Duração:    {cycle_text}\n"
            f"Status:     {status_text}\n"
            f"Início:     {format_date(sub.start_date)}\n"
            f"Expira:     {'Nunca' if is_lifetime else format_date(sub.end_date)}\n"
            f"Renovação:  {renewal}\n"
            f"Valor:      {format_currency(plan.price) if plan else 'N/A'}"
            f"</pre>"
        )

        # Aviso de expiração próxima
        if is_active and not is_lifetime:
            remaining = format_remaining_text(sub.end_date)
            days_left = (sub.end_date - now).total_seconds() / 86400
            if days_left <= 7:
                text += f"\n\n⚠️ Expira em {remaining}"

        # Botões contextuais
        keyboard = []

        if is_active:
            keyboard.append([
                InlineKeyboardButton(f"Entrar no {type_label.capitalize()}", callback_data=f"get_link_{sub.id}")
            ])
            if getattr(sub, 'cancel_at_period_end', False):
                keyboard.append([
                    InlineKeyboardButton("Reativar Renovação", callback_data=f"reactivate_sub_{sub.id}")
                ])
            elif getattr(sub, 'auto_renew', False) and sub.stripe_subscription_id and not getattr(sub, 'is_legacy', False):
                keyboard.append([
                    InlineKeyboardButton("Cancelar Renovação", callback_data=f"cancel_sub_{sub.id}")
                ])
            elif getattr(sub, 'is_legacy', False) or not sub.stripe_subscription_id:
                if not is_lifetime:
                    keyboard.append([
                        InlineKeyboardButton("Renovar Agora", callback_data=f"renew_{sub.id}")
                    ])
            keyboard.append([
                InlineKeyboardButton("💳 Pagamentos", callback_data=f"sub_txns_{sub.id}")
            ])
            keyboard.append([
                InlineKeyboardButton("↩ Voltar", callback_data="subs_active")
            ])
        else:
            # Expirada ou cancelada
            if group:
                keyboard.append([
                    InlineKeyboardButton("🔄 Assinar Novamente", callback_data=f"group_{group.id}")
                ])
            keyboard.append([
                InlineKeyboardButton("💳 Pagamentos", callback_data=f"sub_txns_{sub.id}")
            ])
            keyboard.append([
                InlineKeyboardButton("↩ Voltar", callback_data="subs_history")
            ])

        await query.edit_message_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


# ──────────────────────────────────────────────
# Fase 5: Histórico de Assinaturas
# ──────────────────────────────────────────────

async def show_subscription_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Histórico completo agrupado por grupo — todas as subs reais (não tentativas abandonadas)"""
    query = update.callback_query
    await query.answer()
    user = query.from_user

    # Extrair página
    page = 0
    data = query.data
    if '_p' in data:
        try:
            page = int(data.split('_p')[1])
        except (IndexError, ValueError):
            page = 0

    now = datetime.utcnow()

    with get_db_session() as session:
        # Buscar TODAS as subs do usuário (ativas, expiradas, canceladas com pagamento)
        all_subs = session.query(Subscription).filter(
            Subscription.telegram_user_id == str(user.id),
            Subscription.status.in_(['active', 'expired'])
        ).order_by(Subscription.end_date.desc()).all()

        # Incluir canceladas que tiveram pagamento real (não abandonos)
        cancelled_real = session.query(Subscription).filter(
            Subscription.telegram_user_id == str(user.id),
            Subscription.status == 'cancelled'
        ).all()
        for sub in cancelled_real:
            has_completed = any(t.status == 'completed' for t in sub.transactions)
            if has_completed:
                all_subs.append(sub)

        all_history = all_subs

        # Agrupar por grupo — manter todas as subs por grupo
        groups_subs = {}
        for sub in all_history:
            gid = sub.group_id
            if gid not in groups_subs:
                groups_subs[gid] = []
            groups_subs[gid].append(sub)

        # Para cada grupo: sub mais recente + stats
        groups_map = {}
        groups_stats = {}  # {group_id: (count, total_invested)}
        for gid, subs in groups_subs.items():
            latest = max(subs, key=lambda s: s.end_date or datetime.min)
            groups_map[gid] = latest
            count = len(subs)
            total = sum(
                float(t.amount) for s in subs for t in s.transactions if t.status == 'completed'
            )
            groups_stats[gid] = (count, total)

        grouped = sorted(groups_map.values(), key=lambda s: s.end_date or datetime.min, reverse=True)

        if not grouped:
            text = (
                "📋 <b>Histórico</b>\n\n"
                "Nenhuma assinatura no histórico."
            )
            keyboard = [[InlineKeyboardButton("↩ Voltar", callback_data="back_to_start")]]
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
            return

        total = len(grouped)
        start = page * SUBS_PER_PAGE
        page_items = grouped[start:start + SUBS_PER_PAGE]

        text = "📋 <b>Histórico</b>\n"

        for sub in page_items:
            group = sub.group
            plan = sub.plan
            group_name = escape_html(group.name) if group else "N/A"
            plan_name = escape_html(plan.name) if plan else "N/A"

            sub_count, total_invested = groups_stats.get(sub.group_id, (1, 0))

            if sub.status == 'active' and sub.end_date and sub.end_date > now:
                emoji = "✅"
                date_text = f"Ativa até {format_date(sub.end_date)}"
            elif sub.status == 'cancelled':
                emoji = "🚫"
                date_text = f"Cancelada em {format_date(sub.end_date)}"
            else:
                emoji = "❌"
                date_text = f"Expirou em {format_date(sub.end_date)}"

            text += f"\n{emoji} <b>{group_name}</b>\n"
            text += f"   {plan_name} · {date_text}\n"
            sub_word = "assinatura" if sub_count == 1 else "assinaturas"
            invested_word = "investido" if sub_count == 1 else "investidos"
            text += f"   {sub_count} {sub_word} · {format_currency(total_invested)} {invested_word}\n"

        # Botões: por grupo — timeline + assinar novamente
        keyboard = []
        for sub in page_items:
            group = sub.group
            group_name_short = group.name[:18] if group else "N/A"

            row = [InlineKeyboardButton(f"📋 {group_name_short}", callback_data=f"group_history_{group.id}" if group else f"sub_detail_{sub.id}")]
            # Só mostrar "Assinar" se grupo não tem sub ativa
            is_active = sub.status == 'active' and sub.end_date and sub.end_date > now
            if group and not is_active:
                row.append(InlineKeyboardButton("🔄 Assinar", callback_data=f"group_{group.id}"))
            keyboard.append(row)

        # Paginação
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("⬅️", callback_data=f"subs_history_p{page - 1}"))
        if start + SUBS_PER_PAGE < total:
            nav_row.append(InlineKeyboardButton("➡️", callback_data=f"subs_history_p{page + 1}"))
        if nav_row:
            keyboard.append(nav_row)

        keyboard.append([InlineKeyboardButton("↩ Voltar", callback_data="back_to_start")])

        await query.edit_message_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


# ──────────────────────────────────────────────
# Fase 5b: Timeline por Grupo
# ──────────────────────────────────────────────

def _payment_method_label(sub):
    """Label curto para método de pagamento"""
    method = getattr(sub, 'payment_method_type', None)
    if method == 'boleto':
        return 'Boleto'
    return 'Cartão'


async def show_group_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Timeline completa de assinaturas do usuário em um grupo — callback group_history_{group_id}"""
    query = update.callback_query
    await query.answer()
    user = query.from_user

    group_id = int(query.data.replace("group_history_", ""))

    with get_db_session() as session:
        group = session.query(Group).get(group_id)
        if not group:
            await query.edit_message_text(
                "Grupo não encontrado.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("↩ Voltar", callback_data="subs_history")
                ]])
            )
            return

        group_name = escape_html(group.name)

        # Buscar TODAS as subs do usuário neste grupo (com pagamento real ou ativas/expiradas)
        all_subs = session.query(Subscription).filter(
            Subscription.telegram_user_id == str(user.id),
            Subscription.group_id == group_id
        ).order_by(Subscription.start_date.desc()).all()

        # Filtrar: só subs com pagamento real ou status significativo
        subs = []
        for sub in all_subs:
            if sub.status in ('active', 'expired'):
                subs.append(sub)
            elif sub.status == 'cancelled':
                has_completed = any(t.status == 'completed' for t in sub.transactions)
                if has_completed:
                    subs.append(sub)

        if not subs:
            await query.edit_message_text(
                f"📋 <b>{group_name}</b>\n\nNenhuma assinatura encontrada.",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("↩ Voltar", callback_data="subs_history")
                ]])
            )
            return

        # Stats gerais
        total_invested = sum(
            float(t.amount) for s in subs for t in s.transactions if t.status == 'completed'
        )
        sub_count = len(subs)
        sub_word = "assinatura" if sub_count == 1 else "assinaturas"
        invested_word = "investido" if sub_count == 1 else "investidos"

        text = f"📋 <b>{group_name}</b>\n\n"
        text += f"{sub_count} {sub_word} · {format_currency(total_invested)} {invested_word}\n"
        text += "━━━━━━━━━━━━━━━━━━━━━━\n"

        # Limitar a 3 mais recentes se mais de 5
        display_subs = subs
        hidden_count = 0
        if len(subs) > 5:
            display_subs = subs[:3]
            hidden_count = len(subs) - 3

        now = datetime.utcnow()

        for sub in display_subs:
            plan = sub.plan
            plan_name = escape_html(plan.name) if plan else "N/A"
            plan_price = format_currency(plan.price) if plan else "N/A"

            # Header com período para diferenciar subs do mesmo plano
            start_str = format_date(sub.start_date) if sub.start_date else "?"
            text += f"\n▸ <b>{plan_name}</b> — {plan_price} · desde {start_str}\n"

            # Buscar transações completed, ordenadas por data
            completed_txns = sorted(
                [t for t in sub.transactions if t.status == 'completed'],
                key=lambda t: t.paid_at or t.created_at or datetime.min
            )

            # Verificar se há múltiplas txns no mesmo dia (para mostrar horário)
            txn_dates = [format_date(t.paid_at or t.created_at) for t in completed_txns]
            has_same_day = len(txn_dates) != len(set(txn_dates))

            # Evento: Início — combinar com primeiro pagamento se mesmo dia
            first_txn = completed_txns[0] if completed_txns else None
            first_txn_date = format_date(first_txn.paid_at or first_txn.created_at) if first_txn else None

            if first_txn and (
                getattr(first_txn, 'billing_reason', None) == 'subscription_create'
                or first_txn_date == start_str
            ):
                # Combinar início com primeiro pagamento
                text += f"  🟢 Iniciou em {start_str} · 💳 {format_currency(first_txn.amount)} · {_payment_method_label(sub)}\n"
                remaining_txns = completed_txns[1:]
            else:
                text += f"  🟢 Iniciou em {start_str}\n"
                remaining_txns = completed_txns

            # Eventos de pagamento subsequentes
            for txn in remaining_txns:
                reason = getattr(txn, 'billing_reason', None) or ''
                txn_dt = txn.paid_at or txn.created_at
                txn_date = format_date(txn_dt, include_time=has_same_day)
                txn_amount = format_currency(txn.amount)

                if reason == 'subscription_cycle':
                    text += f"  🔄 Renovou em {txn_date} · {txn_amount}\n"
                elif reason == 'plan_change':
                    text += f"  🔀 Trocou de plano · {txn_amount}\n"
                elif reason == 'lifetime_purchase':
                    text += f"  💳 Pagou {txn_amount} · Vitalício\n"
                else:
                    text += f"  💳 Pagou {txn_amount} em {txn_date}\n"

            # Cancelou renovação?
            if getattr(sub, 'cancel_at_period_end', False) and sub.status == 'active':
                text += "  ⏹ Cancelou renovação\n"

            # Status final
            if sub.status == 'expired' or (sub.status == 'active' and sub.end_date and sub.end_date <= now):
                text += f"  ❌ Expirou em {format_date(sub.end_date)}\n"
            elif sub.status == 'cancelled':
                text += f"  🚫 Cancelada em {format_date(sub.end_date)}\n"
            elif sub.status == 'active' and sub.end_date and sub.end_date > now:
                text += f"  ✅ Ativa até {format_date(sub.end_date)}\n"

        if hidden_count > 0:
            text += f"\n<i>...e mais {hidden_count} anteriores</i>\n"

        # Truncar se necessário (Telegram max 4096)
        if len(text) > 4000:
            text = text[:3990] + "\n..."

        # Botões
        keyboard = []

        # "Assinar novamente" se grupo ativo e sem sub ativa
        has_active = any(
            s.status == 'active' and s.end_date and s.end_date > now
            for s in all_subs
        )
        if group and not has_active:
            keyboard.append([InlineKeyboardButton("🔄 Assinar Novamente", callback_data=f"group_{group.id}")])

        keyboard.append([InlineKeyboardButton("↩ Voltar", callback_data="subs_history")])

        await query.edit_message_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


# ──────────────────────────────────────────────
# Fase 6: Transações por Assinatura
# ──────────────────────────────────────────────

async def show_subscription_transactions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Listar transações de uma assinatura — callback sub_txns_{id}"""
    query = update.callback_query
    await query.answer()
    user = query.from_user

    sub_id = int(query.data.replace("sub_txns_", ""))

    with get_db_session() as session:
        sub = session.query(Subscription).get(sub_id)

        if not sub or sub.telegram_user_id != str(user.id):
            await query.edit_message_text(
                "Assinatura não encontrada.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("Menu", callback_data="back_to_start")
                ]])
            )
            return

        group_name = escape_html(sub.group.name) if sub.group else "N/A"

        transactions = session.query(Transaction).filter_by(
            subscription_id=sub.id
        ).order_by(Transaction.created_at.desc()).all()

        text = f"💳 <b>Pagamentos — {group_name}</b>\n"

        if not transactions:
            text += "\nNenhum pagamento registrado."
        else:
            for txn in transactions:
                if txn.status == 'completed':
                    txn_emoji = "✅"
                elif txn.status == 'pending':
                    txn_emoji = "⏳"
                elif txn.status == 'cancelled':
                    txn_emoji = "❌"
                else:
                    txn_emoji = "⚪"

                txn_date = format_date(txn.paid_at or txn.created_at)
                reason_text = _billing_reason_text(txn.billing_reason)
                method = (txn.payment_method or 'stripe').capitalize()

                text += f"\n{txn_emoji} {txn_date} · {format_currency(txn.amount)}\n"

                if txn.status == 'completed':
                    text += f"   {reason_text} · {method}\n"
                elif txn.status == 'pending':
                    text += f"   Pendente\n"
                elif txn.status == 'cancelled':
                    text += f"   Cancelado\n"
                else:
                    text += f"   {txn.status}\n"

        keyboard = [
            [InlineKeyboardButton("↩ Voltar", callback_data=f"sub_detail_{sub.id}")]
        ]

        await query.edit_message_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
