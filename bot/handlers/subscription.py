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
    format_currency, format_currency_code, escape_html
)
from app import db
from app.models import Subscription, Group, Creator, PricingPlan, Transaction

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

        # Separar por status
        active = [s for s in all_subs if s.status == 'active']
        expired = [s for s in all_subs if s.status == 'expired']
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

                if is_lifetime:
                    emoji = "♾️"
                else:
                    remaining = format_remaining_text(sub.end_date)
                    emoji = get_expiry_emoji(sub.end_date)
                    days_left = (sub.end_date - datetime.utcnow()).days

                    # Classificar urgência
                    if days_left <= 3:
                        need_renewal_urgent.append(sub)
                    elif days_left <= 7:
                        need_renewal_soon.append(sub)

                text += f"\n{emoji} <b>{group_name}</b>\n"
                text += f"   Plano: <code>{plan_name}</code>\n"

                if is_lifetime:
                    text += f"   Acesso vitalício\n"
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
        still_active = sub.status == 'active' and sub.end_date and sub.end_date > now
        amount = float(plan.price)
        platform_fee = amount * 0.10

        checkout_data = {
            'group_id': group.id,
            'plan_id': plan.id,
            'amount': amount,
            'platform_fee': platform_fee,
            'creator_amount': amount - platform_fee,
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
            text += "\n\n<i>Escolha a forma de pagamento:</i>"
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
            Subscription.end_date > now
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
        is_active = sub.status == 'active' and sub.end_date > now

        # Status text
        if is_active:
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

        text = (
            f"{emoji} <b>{group_name}</b>\n"
            f"{type_label.capitalize()}\n\n"
            f"<pre>"
            f"Plano:      {plan_name}\n"
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
    """Histórico agrupado por grupo — só subs reais (não tentativas abandonadas)"""
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
        # Buscar todas as subs não-ativas do usuário
        all_history = session.query(Subscription).filter(
            Subscription.telegram_user_id == str(user.id),
            db.or_(
                Subscription.status == 'expired',
                db.and_(Subscription.status == 'active', Subscription.end_date <= now)
            )
        ).order_by(Subscription.end_date.desc()).all()

        # Também incluir canceladas que tiveram pagamento real (não abandonos)
        cancelled_real = session.query(Subscription).filter(
            Subscription.telegram_user_id == str(user.id),
            Subscription.status == 'cancelled'
        ).all()
        for sub in cancelled_real:
            has_completed = any(t.status == 'completed' for t in sub.transactions)
            if has_completed:
                all_history.append(sub)

        # Agrupar por grupo — manter só a sub mais recente de cada grupo
        groups_map = {}
        for sub in all_history:
            gid = sub.group_id
            if gid not in groups_map or (sub.end_date and sub.end_date > groups_map[gid].end_date):
                groups_map[gid] = sub

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

            # Contar quantas subs reais teve neste grupo
            group_sub_count = sum(1 for s in all_history if s.group_id == sub.group_id)

            if sub.status == 'cancelled':
                emoji = "🚫"
                date_text = f"Cancelada em {format_date(sub.end_date)}"
            else:
                emoji = "❌"
                date_text = f"Expirou em {format_date(sub.end_date)}"

            text += f"\n{emoji} <b>{group_name}</b>\n"
            text += f"   {plan_name} · {date_text}\n"
            if group_sub_count > 1:
                text += f"   ({group_sub_count} assinaturas)\n"

        # Botões: por grupo — detalhes + assinar novamente
        keyboard = []
        for sub in page_items:
            group = sub.group
            group_name_short = group.name[:18] if group else "N/A"

            row = [InlineKeyboardButton(f"📋 {group_name_short}", callback_data=f"sub_detail_{sub.id}")]
            if group:
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
