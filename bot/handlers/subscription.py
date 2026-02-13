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
    """Processar renovação de uma assinatura específica"""
    query = update.callback_query

    with get_db_session() as session:
        sub = session.query(Subscription).get(sub_id)

        if not sub:
            await query.edit_message_text("Assinatura não encontrada.")
            return

        group = sub.group
        plan = sub.plan
        group_name = escape_html(group.name)
        plan_name = escape_html(plan.name)

        # Simular renovação com desconto
        days_left = (sub.end_date - datetime.utcnow()).days

        if days_left >= 5:
            discount = 0.1  # 10% de desconto
        else:
            discount = 0

        final_price = float(plan.price) * (1 - discount)

        text = (
            f"<b>Renovar assinatura</b>\n\n"
            f"<pre>"
            f"Grupo:    {group.name}\n"
            f"Plano:    {plan.name}\n"
            f"Duração:  {plan.duration_days} dias\n"
            f"Valor:    {format_currency(final_price)}"
            f"</pre>"
        )

        if discount > 0:
            text += f"\n\n<i>Desconto de renovação aplicado!</i>"

        # Armazenar dados para pagamento
        context.user_data['renewal'] = {
            'subscription_id': sub_id,
            'group_id': group.id,
            'plan_id': plan.id,
            'amount': final_price,
            'discount': discount
        }

        keyboard = [
            [InlineKeyboardButton("💳 Cartão / Boleto", callback_data="pay_renewal_stripe")],
            [InlineKeyboardButton("⚡ PIX", callback_data="pay_renewal_pix")],
            [InlineKeyboardButton("Cancelar", callback_data="check_renewals")]
        ]

        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def handle_renewal_pix_coming_soon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """PIX para renovação — em desenvolvimento."""
    query = update.callback_query
    await query.answer("PIX em breve!", show_alert=True)


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
                f"Use o botão abaixo para entrar em <b>{group_name}</b>.\n\n"
                f"<i>O link é de uso único.</i>"
            )

            keyboard = [
                [InlineKeyboardButton("Entrar no Grupo", url=invite_link)],
                [InlineKeyboardButton("Menu", callback_data="back_to_start")]
            ]

        except Exception as e:
            logger.error(f"Erro ao gerar invite link: {e}")
            text = (
                f"Não foi possível gerar o link.\n\n"
                f"Contacte o suporte informando assinatura #{sub.id}."
            )
            keyboard = [[InlineKeyboardButton("Menu", callback_data="back_to_start")]]

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
