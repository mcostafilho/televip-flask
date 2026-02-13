"""
Handler de pagamento do bot - Sistema completo de processamento de pagamentos
"""
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from bot.utils.database import get_db_session
from bot.utils.stripe_integration import (
    create_checkout_session,
    get_or_create_stripe_customer, get_or_create_stripe_price,
    create_subscription_checkout
)
from bot.utils.format_utils import (
    format_currency, format_currency_code, format_remaining_text,
    get_expiry_emoji, format_date, format_date_code, escape_html
)
from app.models import Group, PricingPlan, Subscription, Transaction, Creator

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _payment_method_keyboard(group_id):
    """Keyboard padrão: escolha de método de pagamento."""
    return [
        [InlineKeyboardButton("💳 Cartão / Boleto", callback_data="pay_stripe")],
        [InlineKeyboardButton("⚡ PIX", callback_data="pay_pix")],
        [InlineKeyboardButton("↩ Voltar", callback_data=f"group_{group_id}")]
    ]


def _order_summary_text(checkout_data):
    """Texto do resumo do pedido."""
    is_lifetime = checkout_data.get('is_lifetime', False)
    if is_lifetime:
        duration_text = "Vitalício"
        type_text = "Pagamento único"
    else:
        duration_text = f"{checkout_data['duration_days']} dias"
        type_text = "Recorrente"

    return (
        f"<b>Resumo do pedido</b>\n\n"
        f"<pre>"
        f"Grupo:    {checkout_data['group_name']}\n"
        f"Plano:    {checkout_data['plan_name']}\n"
        f"Duração:  {duration_text}\n"
        f"Tipo:     {type_text}\n"
        f"─────────────────────\n"
        f"Total:    {format_currency(checkout_data['amount'])}"
        f"</pre>"
    )


def _cancel_pending(context):
    """Cancela transação/assinatura pendente no banco e limpa contexto."""
    session_id = context.user_data.get('stripe_session_id')
    if session_id:
        try:
            with get_db_session() as session:
                txn = session.query(Transaction).filter_by(
                    stripe_session_id=session_id, status='pending'
                ).first()
                if txn:
                    txn.status = 'cancelled'
                    sub = txn.subscription
                    if sub and sub.status == 'pending':
                        sub.status = 'cancelled'
                    session.commit()
        except Exception as e:
            logger.error(f"Erro ao cancelar pendente: {e}")

    context.user_data.pop('stripe_session_id', None)
    context.user_data.pop('stripe_checkout_url', None)


# ──────────────────────────────────────────────
# Voltar para seleção de planos de um grupo
# ──────────────────────────────────────────────

async def show_group_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostrar planos de um grupo (callback group_<id>)."""
    query = update.callback_query
    await query.answer()

    try:
        group_id = int(query.data.split('_')[1])
    except (IndexError, ValueError):
        await query.edit_message_text(
            "Erro. Use /start para recomeçar.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Menu", callback_data="back_to_start")
            ]])
        )
        return

    with get_db_session() as session:
        group = session.query(Group).get(group_id)
        if not group or not group.is_active:
            await query.edit_message_text(
                "Grupo não disponível.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("Menu", callback_data="back_to_start")
                ]])
            )
            return

        plans = session.query(PricingPlan).filter_by(
            group_id=group.id, is_active=True
        ).order_by(PricingPlan.price).all()

        if not plans:
            await query.edit_message_text(
                "Nenhum plano disponível para este grupo.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("Menu", callback_data="back_to_start")
                ]])
            )
            return

        group_name = escape_html(group.name)
        type_label = "canal" if group.chat_type == 'channel' else "grupo"
        description = escape_html(group.description) if group.description else f"{type_label.capitalize()} VIP exclusivo"

        text = (
            f"Bem-vindo ao {type_label} <b>{group_name}</b>!\n"
            f"{description}\n\n"
            f"<b>Planos disponíveis:</b>\n"
        )

        keyboard = []
        for plan in plans:
            plan_name = escape_html(plan.name)
            text += f"\n<code>{plan_name}</code> — {format_currency(plan.price)} / {plan.duration_days} dias"
            keyboard.append([
                InlineKeyboardButton(
                    f"{plan.name} - {format_currency(plan.price)}",
                    callback_data=f"plan_{group.id}_{plan.id}"
                )
            ])

        text += '\n\n<i>Ao assinar, você concorda com os <a href="https://televip.app/termos">termos de uso</a>.</i>'
        keyboard.append([InlineKeyboardButton("Cancelar", callback_data="cancel")])

        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


# ──────────────────────────────────────────────
# TELA 1: Resumo do pedido + escolha de método
# ──────────────────────────────────────────────

async def start_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostrar resumo do pedido e opções de pagamento."""
    query = update.callback_query
    await query.answer()

    try:
        _, group_id, plan_id = query.data.split('_')
        group_id = int(group_id)
        plan_id = int(plan_id)
    except Exception:
        await query.edit_message_text(
            "Erro ao processar. Tente novamente.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Menu", callback_data="back_to_start")
            ]])
        )
        return

    with get_db_session() as session:
        group = session.query(Group).get(group_id)
        plan = session.query(PricingPlan).get(plan_id)

        if not group or not plan:
            await query.edit_message_text(
                "Grupo ou plano não encontrado.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("Menu", callback_data="back_to_start")
                ]])
            )
            return

        amount = float(plan.price)
        platform_fee = amount * 0.10
        is_lifetime = getattr(plan, 'is_lifetime', False) or plan.duration_days == 0

        checkout_data = {
            'group_id': group_id,
            'plan_id': plan_id,
            'amount': amount,
            'platform_fee': platform_fee,
            'creator_amount': amount - platform_fee,
            'duration_days': plan.duration_days,
            'is_lifetime': is_lifetime,
            'group_name': group.name,
            'plan_name': plan.name
        }

        # Limpar qualquer pendente anterior
        _cancel_pending(context)
        context.user_data['checkout'] = checkout_data

        text = _order_summary_text(checkout_data)
        text += "\n\n<i>Escolha a forma de pagamento:</i>"

        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(_payment_method_keyboard(group_id))
        )


# ──────────────────────────────────────────────
# TELA 2: Método selecionado
# ──────────────────────────────────────────────

async def handle_payment_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processar seleção do método de pagamento."""
    query = update.callback_query
    await query.answer()

    checkout_data = context.user_data.get('checkout')
    if not checkout_data:
        await query.edit_message_text(
            "Sessão expirada. Inicie novamente.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Menu", callback_data="back_to_start")
            ]])
        )
        return

    if query.data == "pay_pix":
        group_id = checkout_data.get('group_id', '')
        await query.edit_message_text(
            "⚡ <b>PIX — Em breve!</b>\n\n"
            "Estamos finalizando a integração.\n"
            "Em breve você poderá pagar com QR Code.\n\n"
            "<i>Por enquanto, use Cartão ou Boleto:</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(_payment_method_keyboard(group_id))
        )
        return

    if query.data == "pay_stripe":
        await _create_stripe_session(query, context, checkout_data)


# ──────────────────────────────────────────────
# TELA 3: Checkout Stripe (link de pagamento)
# ──────────────────────────────────────────────

async def _create_stripe_session(query, context, checkout_data):
    """Criar sessão Stripe e mostrar link de pagamento."""
    user = query.from_user
    bot_username = context.bot.username
    success_url = f"https://t.me/{bot_username}?start=payment_success"
    cancel_url = f"https://t.me/{bot_username}?start=payment_cancel"
    is_lifetime = checkout_data.get('is_lifetime', False)
    group_id = checkout_data['group_id']
    plan_id = checkout_data['plan_id']

    try:
        customer_id = get_or_create_stripe_customer(
            telegram_user_id=str(user.id),
            username=user.username
        )

        with get_db_session() as session:
            plan = session.query(PricingPlan).get(plan_id)
            group = session.query(Group).get(group_id)

            if not plan or not group:
                await query.edit_message_text(
                    "Plano ou grupo não encontrado.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("Menu", callback_data="back_to_start")
                    ]])
                )
                return

            price_id = get_or_create_stripe_price(plan, group)

        metadata = {
            'user_id': str(user.id),
            'username': user.username or '',
            'group_id': str(group_id),
            'plan_id': str(plan_id),
            'group_name': checkout_data['group_name'],
            'plan_name': checkout_data['plan_name']
        }

        if is_lifetime:
            result = await create_checkout_session(
                amount=checkout_data['amount'],
                group_name=checkout_data['group_name'],
                plan_name=checkout_data['plan_name'],
                user_id=str(user.id),
                success_url=success_url,
                cancel_url=cancel_url,
                metadata=metadata
            )
        else:
            result = await create_subscription_checkout(
                customer_id=customer_id,
                price_id=price_id,
                metadata=metadata,
                success_url=success_url,
                cancel_url=cancel_url
            )

        if not result['success']:
            await query.edit_message_text(
                "<b>Erro ao criar pagamento</b>\n\n"
                "Tente novamente em alguns segundos.",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Tentar Novamente", callback_data=f"plan_{group_id}_{plan_id}")],
                    [InlineKeyboardButton("Menu", callback_data="back_to_start")]
                ])
            )
            return

        # Salvar no contexto
        context.user_data['stripe_session_id'] = result['session_id']
        context.user_data['stripe_checkout_url'] = result['url']

        # Criar subscription + transaction pendentes no banco
        with get_db_session() as session:
            if is_lifetime:
                end_date = datetime(2099, 12, 31)
                auto_renew = False
                is_legacy = True
                billing_reason = 'lifetime_purchase'
            else:
                end_date = datetime.utcnow() + timedelta(days=checkout_data['duration_days'])
                auto_renew = True
                is_legacy = False
                billing_reason = 'subscription_create'

            new_sub = Subscription(
                group_id=group_id,
                plan_id=plan_id,
                telegram_user_id=str(user.id),
                telegram_username=user.username,
                stripe_customer_id=customer_id,
                status='pending',
                auto_renew=auto_renew,
                is_legacy=is_legacy,
                start_date=datetime.utcnow(),
                end_date=end_date
            )
            session.add(new_sub)
            session.flush()

            txn = Transaction(
                subscription_id=new_sub.id,
                amount=checkout_data['amount'],
                fee=checkout_data['platform_fee'],
                net_amount=checkout_data['creator_amount'],
                payment_method='stripe',
                stripe_session_id=result['session_id'],
                billing_reason=billing_reason,
                status='pending'
            )
            session.add(txn)
            session.commit()
            logger.info(f"Subscription {new_sub.id} criada (pending) session={result['session_id']}")

        # Mostrar tela do checkout
        await _show_stripe_checkout(query, checkout_data, result['url'])

    except Exception as e:
        logger.error(f"Erro ao processar pagamento: {e}")
        await query.edit_message_text(
            "<b>Erro ao processar pagamento</b>\n\n"
            "Tente novamente ou entre em contato com o suporte.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Tentar Novamente", callback_data=f"plan_{group_id}_{plan_id}")],
                [InlineKeyboardButton("Menu", callback_data="back_to_start")]
            ])
        )


async def _show_stripe_checkout(query, checkout_data, stripe_url):
    """Mostrar tela com link do Stripe."""
    text = (
        f"💳 <b>Pagamento via Cartão / Boleto</b>\n\n"
        f"Valor: <b>{format_currency_code(checkout_data['amount'])}</b>\n\n"
        f"1. Clique em <b>Pagar</b> para abrir o checkout\n"
        f"2. Complete o pagamento\n"
        f"3. Volte aqui e clique em <b>Já Paguei</b>"
    )

    keyboard = [
        [InlineKeyboardButton("Pagar", url=stripe_url)],
        [InlineKeyboardButton("✅ Já Paguei", callback_data="check_payment_status")],
        [InlineKeyboardButton("↩ Trocar Método", callback_data="back_to_methods")],
    ]

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ──────────────────────────────────────────────
# Voltar para seleção de método
# ──────────────────────────────────────────────

async def back_to_methods(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Voltar da tela do Stripe para escolha de método de pagamento."""
    query = update.callback_query
    await query.answer()

    # Cancelar o pendente no banco
    _cancel_pending(context)

    checkout_data = context.user_data.get('checkout')
    if not checkout_data:
        await query.edit_message_text(
            "Sessão expirada. Inicie novamente.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Menu", callback_data="back_to_start")
            ]])
        )
        return

    group_id = checkout_data['group_id']
    text = _order_summary_text(checkout_data)
    text += "\n\n<i>Escolha a forma de pagamento:</i>"

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(_payment_method_keyboard(group_id))
    )


# ──────────────────────────────────────────────
# Desistir do pagamento
# ──────────────────────────────────────────────

async def abandon_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancelar pagamento pendente e voltar ao início."""
    query = update.callback_query
    await query.answer()

    checkout_data = context.user_data.get('checkout')
    _cancel_pending(context)
    context.user_data.pop('checkout', None)

    if checkout_data:
        group_id = checkout_data.get('group_id')
        keyboard = [
            [InlineKeyboardButton("Escolher Plano", callback_data=f"group_{group_id}")],
            [InlineKeyboardButton("Menu Principal", callback_data="back_to_start")]
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("Menu Principal", callback_data="back_to_start")]
        ]

    await query.edit_message_text(
        "Pagamento cancelado.\n"
        "<i>Nenhuma cobrança foi realizada.</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ──────────────────────────────────────────────
# Assinaturas do usuário
# ──────────────────────────────────────────────

async def list_user_subscriptions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Listar assinaturas ativas do usuário"""
    query = update.callback_query
    if query:
        await query.answer()
        user = query.from_user
        message = query
    else:
        user = update.effective_user
        message = update

    with get_db_session() as session:
        subscriptions = session.query(Subscription).filter(
            Subscription.telegram_user_id == str(user.id),
            Subscription.status == 'active',
            Subscription.end_date > datetime.utcnow()
        ).all()

        if not subscriptions:
            text = (
                "<b>Suas assinaturas</b>\n\n"
                "Você não tem assinaturas ativas.\n"
                "Use o link de convite de um grupo para assinar."
            )
            keyboard = [[InlineKeyboardButton("Menu", callback_data="back_to_start")]]
        else:
            text = "<b>Suas assinaturas</b>\n"

            for sub in subscriptions:
                group = sub.group
                plan = sub.plan
                is_lifetime = getattr(plan, 'is_lifetime', False) or plan.duration_days == 0
                group_name = escape_html(group.name)
                plan_name = escape_html(plan.name)

                if is_lifetime:
                    expiry_text = "Acesso vitalício"
                else:
                    expiry_text = f"Expira: {format_date_code(sub.end_date)}"

                emoji = get_expiry_emoji(sub.end_date) if not is_lifetime else "♾️"

                text += (
                    f"\n{emoji} <b>{group_name}</b>\n"
                    f"   <code>{plan_name}</code> · {expiry_text}\n"
                )

            keyboard = [[InlineKeyboardButton("Menu", callback_data="back_to_start")]]

        if hasattr(message, 'edit_message_text'):
            await message.edit_message_text(text, parse_mode=ParseMode.HTML,
                                            reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await message.reply_text(text, parse_mode=ParseMode.HTML,
                                     reply_markup=InlineKeyboardMarkup(keyboard))


# ──────────────────────────────────────────────
# Handlers legados / aliases
# ──────────────────────────────────────────────

async def handle_plan_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_payment(update, context)

async def handle_payment_success(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Legacy alias — payment verification is handled by payment_verification.py"""
    from bot.handlers.payment_verification import check_payment_status as verify_status
    await verify_status(update, context)

async def handle_payment_error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Erro no pagamento", show_alert=True)
    checkout_data = context.user_data.get('checkout')
    if checkout_data:
        keyboard = [
            [InlineKeyboardButton("Tentar Novamente", callback_data=f"plan_{checkout_data['group_id']}_{checkout_data['plan_id']}")],
            [InlineKeyboardButton("Menu", callback_data="back_to_start")]
        ]
    else:
        keyboard = [[InlineKeyboardButton("Menu", callback_data="back_to_start")]]

    await query.edit_message_text(
        "<b>Erro no pagamento</b>\n\n"
        "Tente novamente ou entre em contato com o suporte.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ──────────────────────────────────────────────
# Registro de handlers
# ──────────────────────────────────────────────

def register_payment_handlers(application):
    """Registrar todos os handlers de pagamento"""
    from telegram.ext import CallbackQueryHandler, CommandHandler

    application.add_handler(CallbackQueryHandler(start_payment, pattern=r'^plan_\d+_\d+$'))
    application.add_handler(CallbackQueryHandler(handle_payment_method, pattern='^pay_(stripe|pix)$'))
    application.add_handler(CallbackQueryHandler(list_user_subscriptions, pattern='^my_subscriptions$'))
    application.add_handler(CommandHandler('subscriptions', list_user_subscriptions))

    logger.info("Handlers de pagamento registrados")
