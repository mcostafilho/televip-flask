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

def _payment_method_keyboard(group_id, card_only=False):
    """Keyboard padrão: escolha de método de pagamento."""
    if card_only:
        return [
            [InlineKeyboardButton("💳 Cartão", callback_data="pay_stripe")],
            [InlineKeyboardButton("↩ Voltar", callback_data=f"group_{group_id}")]
        ]
    return [
        [InlineKeyboardButton("💳 Cartão / Boleto", callback_data="pay_stripe")],
        [InlineKeyboardButton("⚡ PIX", callback_data="pay_pix")],
        [InlineKeyboardButton("↩ Voltar", callback_data=f"group_{group_id}")]
    ]


def _order_summary_text(checkout_data):
    """Texto do resumo do pedido."""
    is_lifetime = checkout_data.get('is_lifetime', False)
    is_renewal = checkout_data.get('is_renewal', False)
    has_trial = 'trial_end' in checkout_data
    is_plan_change = has_trial and not is_renewal

    if is_lifetime:
        duration_text = "Vitalício"
        type_text = "Pagamento único"
    else:
        duration_text = f"{checkout_data['duration_days']} dias"
        type_text = "Recorrente"

    if is_plan_change:
        title = "Troca de plano"
    elif is_renewal:
        title = "Renovação"
    else:
        title = "Resumo do pedido"

    text = (
        f"<b>{title}</b>\n\n"
        f"<pre>"
        f"Grupo:    {checkout_data['group_name']}\n"
        f"Plano:    {checkout_data['plan_name']}\n"
        f"Duração:  {duration_text}\n"
        f"Tipo:     {type_text}\n"
        f"─────────────────────\n"
        f"Total:    {format_currency(checkout_data['amount'])}"
        f"</pre>"
    )

    if has_trial:
        from datetime import datetime as dt
        trial_dt = dt.utcfromtimestamp(checkout_data['trial_end'])
        new_end = trial_dt + timedelta(days=checkout_data['duration_days'])
        action = "A renovação começa" if is_renewal else "O novo plano começa"
        text += (
            f"\n\n📌 Seu plano atual continua válido.\n"
            f"{action} em <code>{format_date(trial_dt)}</code>\n"
            f"e vale até <code>{format_date(new_end)}</code>.\n\n"
            f"<i>Seu cartão será cobrado somente na data de início.</i>"
        )

    return text


def _cancel_pending(context, telegram_user_id=None):
    """Cancela transação/assinatura pendente no banco e limpa contexto.
    Se telegram_user_id fornecido, cancela TODAS as pendentes do usuário.
    """
    try:
        with get_db_session() as session:
            if telegram_user_id:
                # Cancelar TODAS as transações pendentes do usuário
                pending_txns = session.query(Transaction).join(
                    Subscription
                ).filter(
                    Subscription.telegram_user_id == str(telegram_user_id),
                    Transaction.status == 'pending'
                ).all()
                for txn in pending_txns:
                    txn.status = 'cancelled'
                    sub = txn.subscription
                    if sub and sub.status == 'pending':
                        sub.status = 'cancelled'
                if pending_txns:
                    session.commit()
                    logger.info(f"Canceladas {len(pending_txns)} transações pendentes do usuário {telegram_user_id}")
            else:
                # Fallback: cancelar por session_id do contexto
                session_id = context.user_data.get('stripe_session_id')
                if session_id:
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
        if not group:
            await query.edit_message_text(
                "Grupo não encontrado.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("↩ Voltar", callback_data="back_to_start")
                ]])
            )
            return

        group_name = escape_html(group.name)

        if not group.is_active:
            await query.edit_message_text(
                f"O {('canal' if group.chat_type == 'channel' else 'grupo')} <b>{group_name}</b> "
                f"está temporariamente indisponível.",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("↩ Voltar", callback_data="back_to_start")
                ]])
            )
            return

        plans = session.query(PricingPlan).filter_by(
            group_id=group.id, is_active=True
        ).order_by(PricingPlan.price).all()

        if not plans:
            await query.edit_message_text(
                f"O criador de <b>{group_name}</b> pausou novas assinaturas.\n\n"
                f"Tente novamente mais tarde.",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("↩ Voltar", callback_data="back_to_start")
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
# Trocar plano (assinante ativo)
# ──────────────────────────────────────────────

async def show_change_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostrar planos para troca — exclui plano atual, avisa sobre vigência."""
    query = update.callback_query
    await query.answer()
    user = query.from_user

    try:
        group_id = int(query.data.replace("change_plan_", ""))
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
        if not group:
            await query.edit_message_text(
                "Grupo não encontrado.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("↩ Voltar", callback_data="back_to_start")
                ]])
            )
            return

        # Buscar assinatura ativa do usuário neste grupo
        existing_sub = session.query(Subscription).filter_by(
            group_id=group.id,
            telegram_user_id=str(user.id),
            status='active'
        ).first()

        current_plan_id = existing_sub.plan_id if existing_sub else None

        # Buscar outros planos (excluir o atual)
        plans_query = session.query(PricingPlan).filter_by(
            group_id=group.id, is_active=True
        ).order_by(PricingPlan.price)

        if current_plan_id:
            plans_query = plans_query.filter(PricingPlan.id != current_plan_id)

        plans = plans_query.all()

        group_name = escape_html(group.name)
        type_label = "canal" if group.chat_type == 'channel' else "grupo"

        if not plans:
            await query.edit_message_text(
                f"Não há outros planos disponíveis para <b>{group_name}</b>.",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("↩ Voltar", callback_data="back_to_start")
                ]])
            )
            return

        text = f"<b>Trocar plano — {group_name}</b>\n\n"

        if existing_sub and existing_sub.end_date:
            text += (
                f"Seu plano atual continua até "
                f"<code>{format_date(existing_sub.end_date)}</code>.\n"
                f"O novo plano entra em vigor após o vencimento.\n\n"
            )

        text += "<b>Planos disponíveis:</b>\n"

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
        keyboard.append([InlineKeyboardButton("↩ Voltar", callback_data="back_to_start")])

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

        # Verificar se já tem assinatura ativa neste grupo (troca de plano)
        user = query.from_user
        existing_sub = session.query(Subscription).filter(
            Subscription.group_id == group_id,
            Subscription.telegram_user_id == str(user.id),
            Subscription.status == 'active',
            Subscription.end_date > datetime.utcnow()
        ).first()

        if existing_sub and not is_lifetime:
            # Troca de plano: novo plano começa após vencimento do atual
            checkout_data['existing_sub_id'] = existing_sub.id
            checkout_data['trial_end'] = int(existing_sub.end_date.timestamp())

        # Limpar qualquer pendente anterior
        _cancel_pending(context)
        context.user_data['checkout'] = checkout_data

        text = _order_summary_text(checkout_data)

        # Boleto indisponível para: troca de plano (trial_end) ou planos curtos (≤ 4 dias)
        short_plan = not is_lifetime and plan.duration_days <= 4
        if checkout_data.get('card_only'):
            short_plan = True  # propagate from renewal

        if checkout_data.get('trial_end'):
            # Troca de plano: só cartão (cobrança futura)
            text += "\n\n<i>Confirme com seu cartão:</i>"
            keyboard = [
                [InlineKeyboardButton("💳 Confirmar com Cartão", callback_data="pay_stripe")],
                [InlineKeyboardButton("↩ Voltar", callback_data=f"change_plan_{group_id}")]
            ]
        elif short_plan:
            # Plano curto: boleto não dá tempo de compensar
            text += "\n\n<i>Escolha a forma de pagamento:</i>"
            checkout_data['card_only'] = True
            keyboard = _payment_method_keyboard(group_id, card_only=True)
        else:
            text += "\n\n<i>Escolha a forma de pagamento:</i>"
            keyboard = _payment_method_keyboard(group_id)

        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
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
            'plan_name': checkout_data['plan_name'],
        }
        if checkout_data.get('card_only'):
            metadata['card_only'] = 'true'

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
            trial_end = checkout_data.get('trial_end')
            result = await create_subscription_checkout(
                customer_id=customer_id,
                price_id=price_id,
                metadata=metadata,
                success_url=success_url,
                cancel_url=cancel_url,
                trial_end=trial_end
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

            # Troca de plano: cancelar sub antiga no período e ajustar datas
            start_date = datetime.utcnow()
            existing_sub_id = checkout_data.get('existing_sub_id')
            if existing_sub_id:
                import stripe as stripe_lib
                old_sub = session.query(Subscription).get(existing_sub_id)
                if old_sub and old_sub.status == 'active':
                    # Cancelar Stripe subscription antiga no período
                    if old_sub.stripe_subscription_id and not old_sub.is_legacy:
                        try:
                            stripe_lib.Subscription.modify(
                                old_sub.stripe_subscription_id,
                                cancel_at_period_end=True
                            )
                        except Exception as e:
                            logger.warning(f"Não foi possível cancelar sub antiga no Stripe: {e}")
                    old_sub.cancel_at_period_end = True
                    old_sub.auto_renew = False
                    session.flush()
                    logger.info(f"Sub antiga {old_sub.id} marcada para cancelar no período (troca de plano)")

                    # Novo plano começa após vencimento do atual
                    start_date = old_sub.end_date
                    end_date = start_date + timedelta(days=checkout_data['duration_days'])
                    billing_reason = 'plan_change'

            new_sub = Subscription(
                group_id=group_id,
                plan_id=plan_id,
                telegram_user_id=str(user.id),
                telegram_username=user.username,
                stripe_customer_id=customer_id,
                status='pending',
                auto_renew=auto_renew,
                is_legacy=is_legacy,
                start_date=start_date,
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

        # Agendar verificação automática de pagamento
        try:
            await _schedule_payment_check(
                context, user,
                chat_id=query.message.chat_id,
                message_id=query.message.message_id,
                session_id=result['session_id']
            )
        except Exception as e:
            logger.warning(f"Não foi possível agendar auto-check: {e}")

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


async def _schedule_payment_check(context, user, chat_id, message_id, session_id):
    """Agendar verificação automática de pagamento após checkout."""
    if not context.job_queue:
        logger.info("job_queue indisponível, auto-check não agendado")
        return

    # Cancelar job anterior se existir
    job_name = f"payment_check_{user.id}"
    current_jobs = context.job_queue.get_jobs_by_name(job_name)
    for job in current_jobs:
        job.schedule_removal()

    context.job_queue.run_repeating(
        _auto_check_payment,
        interval=15,
        first=20,  # primeira verificação após 20s
        data={
            'user_id': user.id,
            'chat_id': chat_id,
            'message_id': message_id,
            'session_id': session_id,
            'attempts': 0,
        },
        name=job_name,
    )
    logger.info(f"Auto-check de pagamento agendado para user {user.id}")


async def _auto_check_payment(context: ContextTypes.DEFAULT_TYPE):
    """Job que verifica automaticamente se o pagamento foi confirmado."""
    job = context.job
    data = job.data
    user_id = data['user_id']
    chat_id = data['chat_id']
    message_id = data['message_id']
    session_id = data['session_id']

    data['attempts'] = data.get('attempts', 0) + 1

    # Timeout: 60 tentativas × 15s = 15 minutos
    if data['attempts'] > 60:
        logger.info(f"Auto-check timeout para user {user_id} session {session_id}")
        job.schedule_removal()
        return

    try:
        with get_db_session() as session:
            txn = session.query(Transaction).filter_by(
                stripe_session_id=session_id
            ).first()

            if not txn:
                job.schedule_removal()
                return

            # Já processado (pelo webhook ou pelo botão "Já Paguei")
            if txn.status == 'completed':
                sub = txn.subscription
                if not sub:
                    job.schedule_removal()
                    return

                group = sub.group
                if not group:
                    job.schedule_removal()
                    return

                type_label = "canal" if group.chat_type == 'channel' else "grupo"
                group_name = escape_html(group.name)
                plan_name = escape_html(sub.plan.name) if sub.plan else "N/A"

                # Gerar link de convite
                invite_link = None
                if group.telegram_id:
                    try:
                        link_obj = await context.bot.create_chat_invite_link(
                            chat_id=int(group.telegram_id),
                            member_limit=1,
                            expire_date=datetime.utcnow() + timedelta(days=7),
                            creates_join_request=False
                        )
                        invite_link = link_obj.invite_link
                    except Exception as e:
                        logger.warning(f"Auto-check: erro ao criar invite link: {e}")

                text = (
                    f"<b>Pagamento confirmado!</b>\n\n"
                    f"<pre>"
                    f"{type_label.capitalize()}:  {group.name}\n"
                    f"Plano:      {sub.plan.name if sub.plan else 'N/A'}\n"
                    f"Validade:   {format_date(sub.end_date)}\n"
                    f"Valor:      {format_currency(txn.amount)}"
                    f"</pre>\n\n"
                )

                keyboard = []
                if invite_link:
                    text += (
                        f"Clique abaixo para entrar no {type_label}.\n"
                        f"<i>O link é de uso único — não compartilhe.</i>"
                    )
                    keyboard.append([InlineKeyboardButton(
                        f"Entrar no {type_label.capitalize()}", url=invite_link
                    )])

                keyboard.append([InlineKeyboardButton("Minhas Assinaturas", callback_data="subs_active")])

                try:
                    await context.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                    logger.info(f"Auto-check: mensagem atualizada para user {user_id}")
                except Exception as e:
                    # Mensagem pode já ter sido editada pelo botão "Já Paguei"
                    logger.debug(f"Auto-check: não conseguiu editar mensagem: {e}")

                job.schedule_removal()
                return

            # Cancelado ou falhou
            if txn.status in ('cancelled', 'failed'):
                job.schedule_removal()
                return

            # Ainda pendente — verificar diretamente no Stripe a cada 3 tentativas
            if data['attempts'] % 3 == 0:
                from bot.utils.stripe_integration import verify_payment
                is_paid = await verify_payment(session_id)
                if is_paid:
                    # Stripe confirmou, mas webhook pode estar atrasado
                    # Ativar a subscription aqui (idempotente)
                    sub = txn.subscription
                    if sub and sub.status == 'pending':
                        sub.status = 'active'
                        txn.status = 'completed'
                        txn.paid_at = datetime.utcnow()

                        # Creditar criador
                        group = sub.group
                        if group and group.creator:
                            creator = group.creator
                            net = txn.net_amount or txn.amount or 0
                            if creator.balance is None:
                                creator.balance = 0
                            creator.balance += net
                            if creator.total_earned is None:
                                creator.total_earned = 0
                            creator.total_earned += net

                        session.commit()
                        logger.info(f"Auto-check: subscription {sub.id} ativada (Stripe confirmou)")
                    # Próxima iteração vai pegar txn.status == 'completed' e editar msg

    except Exception as e:
        logger.error(f"Auto-check erro para user {user_id}: {e}")


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
        [InlineKeyboardButton("❌ Desistir", callback_data="abandon_payment")],
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
    card_only = checkout_data.get('card_only', False)
    text = _order_summary_text(checkout_data)
    text += "\n\n<i>Escolha a forma de pagamento:</i>"

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(_payment_method_keyboard(group_id, card_only=card_only))
    )


# ──────────────────────────────────────────────
# Desistir do pagamento
# ──────────────────────────────────────────────

async def abandon_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancelar pagamento pendente e voltar ao início."""
    query = update.callback_query
    await query.answer()
    user = query.from_user

    # Cancelar job de auto-check
    if context.job_queue:
        job_name = f"payment_check_{user.id}"
        for job in context.job_queue.get_jobs_by_name(job_name):
            job.schedule_removal()

    checkout_data = context.user_data.get('checkout')
    _cancel_pending(context, telegram_user_id=user.id)
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
