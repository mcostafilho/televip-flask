"""
Webhooks para processar notificações de pagamento do Stripe
"""
from flask import Blueprint, request, jsonify
import stripe
import os
import logging
import requests
from datetime import datetime, timedelta, timezone
from app import db

# Fuso horário de Brasília (UTC-3)
BRT = timezone(timedelta(hours=-3))

def _fmt_date_brt(dt):
    """Formatar datetime UTC para dd/mm/yyyy em BRT"""
    if dt is None:
        return 'N/A'
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BRT).strftime('%d/%m/%Y')
from app.models import Transaction, Subscription, Creator, Group, PricingPlan

bp = Blueprint('webhooks', __name__, url_prefix='/webhooks')
logger = logging.getLogger(__name__)

# Configurar Stripe
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')


@bp.route('/stripe', methods=['POST'])
def stripe_webhook():
    """Processar webhooks do Stripe - VERSÃO CORRIGIDA"""
    logger.info("=== WEBHOOK RECEBIDO DO STRIPE ===")
    
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature')
    
    logger.info(f"Signature header presente: {'Sim' if sig_header else 'Não'}")
    
    # Verificar assinatura
    webhook_secret = os.getenv('STRIPE_WEBHOOK_SECRET')
    
    if not webhook_secret:
        logger.error("STRIPE_WEBHOOK_SECRET não configurado!")
        return jsonify({'error': 'Webhook secret not configured'}), 500
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
    except ValueError as e:
        logger.error(f"Invalid payload: {e}")
        return jsonify({'error': 'Invalid payload'}), 400
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Invalid signature: {e}")
        return jsonify({'error': 'Invalid signature'}), 400
    
    # Log do evento recebido
    logger.info(f"Event type: {event['type']}")
    logger.info(f"Event ID: {event['id']}")
    
    # Processar diferentes tipos de eventos
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        handle_checkout_session_completed(session)
        
    elif event['type'] == 'payment_intent.succeeded':
        payment_intent = event['data']['object']
        handle_payment_intent_succeeded(payment_intent)
        
    elif event['type'] == 'payment_intent.payment_failed':
        payment_intent = event['data']['object']
        handle_payment_failed(payment_intent)
        
    elif event['type'] == 'invoice.paid':
        invoice = event['data']['object']
        handle_invoice_paid(invoice)

    elif event['type'] == 'invoice.payment_failed':
        invoice = event['data']['object']
        handle_invoice_payment_failed(invoice)

    elif event['type'] == 'customer.subscription.deleted':
        stripe_subscription = event['data']['object']
        handle_subscription_deleted(stripe_subscription)

    elif event['type'] == 'charge.dispute.created':
        dispute = event['data']['object']
        handle_dispute_created(dispute)

    return jsonify({'status': 'success'}), 200


def handle_checkout_session_completed(session):
    """Processar checkout completo - suporta mode='payment' (legacy) e mode='subscription'"""
    logger.info(f"=== PROCESSANDO CHECKOUT SESSION COMPLETO ===")
    logger.info(f"Session ID: {session['id']}")
    logger.info(f"Mode: {session.get('mode')}")
    logger.info(f"Payment status: {session.get('payment_status')}")
    logger.info(f"Metadata: {session.get('metadata')}")

    mode = session.get('mode', 'payment')

    if mode == 'subscription':
        # Subscription mode: store stripe_subscription_id.
        # Actual activation happens via invoice.paid webhook.
        try:
            stripe_sub_id = session.get('subscription')
            session_id = session['id']
            metadata = session.get('metadata', {})

            logger.info(f"Subscription checkout: stripe_sub_id={stripe_sub_id}")

            # Find our pending subscription by the checkout session_id on its transaction
            transaction = Transaction.query.filter_by(
                stripe_session_id=session_id
            ).first()

            if transaction and transaction.subscription:
                sub = transaction.subscription
                if stripe_sub_id:
                    sub.stripe_subscription_id = stripe_sub_id
                db.session.commit()
                logger.info(f"Stored stripe_subscription_id={stripe_sub_id} on subscription {sub.id}")
            else:
                logger.warning(f"No pending transaction found for session {session_id}")

        except Exception as e:
            logger.error(f"Error processing subscription checkout: {e}")
            db.session.rollback()
        return

    # Legacy mode='payment' — original logic
    if session.get('payment_status') != 'paid':
        logger.warning(f"Pagamento nao esta pago. Status: {session.get('payment_status')}")
        return

    try:
        metadata = session.get('metadata', {})
        if not metadata:
            logger.error("Metadata vazio no checkout session")
            return

        transaction_id = metadata.get('transaction_id')
        subscription_id = metadata.get('subscription_id')

        if not transaction_id:
            logger.error("Transaction ID nao encontrado nos metadados")
            return

        transaction = Transaction.query.filter_by(
            id=int(transaction_id),
            status='pending'
        ).first()

        if not transaction:
            logger.error(f"Transacao {transaction_id} nao encontrada ou ja processada")
            return

        transaction.status = 'completed'
        transaction.stripe_payment_intent_id = session.get('payment_intent')
        transaction.paid_at = datetime.utcnow()

        subscription = transaction.subscription
        if not subscription:
            logger.error("Assinatura nao encontrada para a transacao")
            return

        subscription.status = 'active'
        subscription.is_legacy = True
        subscription.start_date = datetime.utcnow()

        plan = subscription.plan
        if plan and plan.duration_days:
            subscription.end_date = subscription.start_date + timedelta(days=plan.duration_days)

        group = subscription.group
        creator = group.creator

        if creator:
            if creator.balance is None:
                creator.balance = 0
            creator.balance += transaction.net_amount
            if creator.total_earned is None:
                creator.total_earned = 0
            creator.total_earned += transaction.net_amount

        db.session.commit()

        logger.info(f"Assinatura legacy {subscription.id} ativada com sucesso!")

        notify_bot_payment_complete(subscription, transaction)

    except Exception as e:
        logger.error(f"Erro ao processar checkout session: {str(e)}")
        db.session.rollback()
        raise


def handle_payment_intent_succeeded(payment_intent):
    """Processar payment intent bem-sucedido"""
    logger.info(f"Payment Intent succeeded: {payment_intent['id']}")
    # O processamento principal é feito no checkout.session.completed
    # Este evento é apenas para log


def handle_payment_failed(payment_intent):
    """Processar falha de pagamento"""
    logger.error(f"Payment Intent failed: {payment_intent['id']}")
    
    metadata = payment_intent.get('metadata', {})
    transaction_id = metadata.get('transaction_id')
    
    if transaction_id:
        transaction = Transaction.query.get(int(transaction_id))
        if transaction and transaction.status == 'pending':
            transaction.status = 'failed'
            transaction.failure_reason = payment_intent.get('last_payment_error', {}).get('message')
            db.session.commit()


def handle_dispute_created(dispute):
    """Processar criação de disputa — suspender assinatura e remover usuario do grupo"""
    logger.warning(f"Disputa criada: {dispute['id']}")

    # Buscar transação pelo payment intent
    payment_intent = dispute.get('payment_intent')
    if not payment_intent:
        logger.warning("Dispute sem payment_intent, ignorando")
        return

    transaction = Transaction.query.filter_by(
        stripe_payment_intent_id=payment_intent
    ).first()

    if not transaction:
        logger.warning(f"Transacao nao encontrada para payment_intent={payment_intent}")
        return

    transaction.status = 'disputed'

    subscription = transaction.subscription
    if subscription:
        subscription.status = 'suspended'
        db.session.commit()

        # Remover usuario do grupo imediatamente
        remove_user_from_group_via_bot(subscription)

        # Notificar usuario
        group_name = subscription.group.name if subscription.group else 'N/A'
        group_name_safe = group_name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        notify_user_via_bot(
            subscription.telegram_user_id,
            f"<b>Assinatura suspensa</b>\n\n"
            f"Sua assinatura de <b>{group_name_safe}</b> foi suspensa "
            f"devido a uma disputa de pagamento."
        )

        # Notificar criador
        creator = subscription.group.creator if subscription.group else None
        if creator and creator.telegram_id:
            notify_user_via_bot(
                creator.telegram_id,
                f"<b>Alerta de chargeback</b>\n\n"
                f"Uma disputa foi aberta para a assinatura de <b>{group_name_safe}</b>.\n"
                f"Assinante: <code>{subscription.telegram_user_id}</code>"
            )

        logger.warning(
            f"Dispute: usuario {subscription.telegram_user_id} removido do grupo "
            f"{subscription.group_id}, assinatura {subscription.id} suspensa"
        )
    else:
        db.session.commit()


def notify_bot_payment_complete(subscription, transaction):
    """Notificar o bot que o pagamento foi completado"""
    bot_token = os.getenv('BOT_TOKEN') or os.getenv('TELEGRAM_BOT_TOKEN')

    if not bot_token:
        logger.error("Bot token não configurado")
        return

    try:
        # Generate single-use invite link via Bot API
        invite_link = subscription.group.invite_link  # fallback
        group = subscription.group
        if group.telegram_id:
            try:
                create_link_url = f"https://api.telegram.org/bot{bot_token}/createChatInviteLink"
                link_response = requests.post(create_link_url, json={
                    'chat_id': int(group.telegram_id),
                    'member_limit': 1
                })
                link_data = link_response.json()
                if link_data.get('ok'):
                    invite_link = link_data['result']['invite_link']
                    logger.info(f"Created single-use invite link for group {group.telegram_id}")
                else:
                    logger.warning(f"Failed to create invite link: {link_data}. Using permanent link.")
            except Exception as e:
                logger.warning(f"Error creating single-use invite link: {e}. Using permanent link.")

        # URL da API do Telegram
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

        # Mensagem para o usuário
        group_name = subscription.group.name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        text = (
            f"<b>Pagamento aprovado!</b>\n\n"
            f"<pre>"
            f"Grupo:     {subscription.group.name}\n"
            f"Válida até: {_fmt_date_brt(subscription.end_date)}\n"
            f"Valor:     R$ {transaction.amount:.2f}"
            f"</pre>\n\n"
            f"Use o link abaixo para acessar o grupo:\n"
            f"{invite_link}\n\n"
            f"<i>Obrigado por assinar!</i>"
        )

        # Enviar mensagem
        response = requests.post(url, json={
            'chat_id': subscription.telegram_user_id,
            'text': text,
            'parse_mode': 'HTML'
        })

        if response.status_code == 200:
            logger.info(f"Usuário {subscription.telegram_user_id} notificado do pagamento")
        else:
            logger.error(f"Erro ao notificar usuário: {response.text}")

    except Exception as e:
        logger.error(f"Erro ao notificar bot: {str(e)}")


def handle_invoice_paid(invoice):
    """Handle invoice.paid — core handler for subscription activation and renewal"""
    logger.info(f"=== INVOICE PAID ===")
    stripe_sub_id = invoice.get('subscription')
    billing_reason = invoice.get('billing_reason', '')  # subscription_create or subscription_cycle
    stripe_invoice_id = invoice.get('id')

    logger.info(f"Invoice {stripe_invoice_id}, subscription={stripe_sub_id}, reason={billing_reason}")

    if not stripe_sub_id:
        logger.info("Invoice not tied to a subscription, skipping")
        return

    try:
        # Idempotency check: don't process same invoice twice
        existing_txn = Transaction.query.filter_by(stripe_invoice_id=stripe_invoice_id).first()
        if existing_txn:
            logger.info(f"Invoice {stripe_invoice_id} already processed (txn {existing_txn.id}), skipping")
            return

        # Find our subscription by stripe_subscription_id
        subscription = Subscription.query.filter_by(
            stripe_subscription_id=stripe_sub_id
        ).first()

        if not subscription:
            logger.warning(f"No subscription found for stripe_sub_id={stripe_sub_id}")
            return

        plan = subscription.plan
        group = subscription.group
        creator = group.creator

        # Detect payment method type from invoice
        payment_method_type = 'card'
        lines = invoice.get('lines', {}).get('data', [])
        if lines:
            pm_types = invoice.get('payment_settings', {}).get('payment_method_types', [])
            if 'boleto' in pm_types:
                payment_method_type = 'boleto'
        # Also check charge payment method
        charge_id = invoice.get('charge')
        if charge_id:
            try:
                charge = stripe.Charge.retrieve(charge_id)
                pm_detail = charge.get('payment_method_details', {})
                if pm_detail.get('type') == 'boleto':
                    payment_method_type = 'boleto'
                elif pm_detail.get('type') == 'card':
                    payment_method_type = 'card'
            except Exception:
                pass

        subscription.payment_method_type = payment_method_type

        amount_paid = invoice.get('amount_paid', 0) / 100  # cents to BRL

        if billing_reason == 'subscription_create':
            # First payment — activate subscription
            logger.info(f"Activating subscription {subscription.id} (first payment)")

            subscription.status = 'active'
            subscription.start_date = datetime.utcnow()
            subscription.end_date = datetime.utcnow() + timedelta(days=plan.duration_days)

            # Find existing transaction for this subscription (pending or already completed by bot)
            existing_txn = Transaction.query.filter_by(
                subscription_id=subscription.id,
                billing_reason='subscription_create'
            ).order_by(Transaction.created_at.desc()).first()

            already_credited = False

            if existing_txn:
                already_credited = existing_txn.status == 'completed'
                existing_txn.status = 'completed'
                existing_txn.paid_at = existing_txn.paid_at or datetime.utcnow()
                existing_txn.stripe_invoice_id = stripe_invoice_id
                pending_txn = existing_txn
            else:
                # No transaction found at all — create one
                txn = Transaction(
                    subscription_id=subscription.id,
                    amount=amount_paid,
                    payment_method='stripe',
                    status='completed',
                    paid_at=datetime.utcnow(),
                    stripe_invoice_id=stripe_invoice_id,
                    billing_reason='subscription_create'
                )
                db.session.add(txn)
                db.session.flush()
                pending_txn = txn

            # Credit creator only if not already credited by bot verification
            if not already_credited and creator:
                if creator.balance is None:
                    creator.balance = 0
                creator.balance += pending_txn.net_amount
                if creator.total_earned is None:
                    creator.total_earned = 0
                creator.total_earned += pending_txn.net_amount
            elif already_credited:
                logger.info(f"Transaction {pending_txn.id} already completed — skipping creator credit")

            db.session.commit()

            logger.info(f"Subscription {subscription.id} activated until {subscription.end_date}")

            # Notify user with invite link
            notify_bot_payment_complete(subscription, pending_txn)

        elif billing_reason == 'subscription_cycle':
            # Renewal — extend end_date
            logger.info(f"Renewing subscription {subscription.id}")

            # Extend from current end_date (not from now, to avoid gaps)
            if subscription.end_date and subscription.end_date > datetime.utcnow():
                subscription.end_date = subscription.end_date + timedelta(days=plan.duration_days)
            else:
                subscription.end_date = datetime.utcnow() + timedelta(days=plan.duration_days)

            subscription.status = 'active'

            # Create renewal transaction
            txn = Transaction(
                subscription_id=subscription.id,
                amount=amount_paid,
                payment_method='stripe',
                status='completed',
                paid_at=datetime.utcnow(),
                stripe_invoice_id=stripe_invoice_id,
                billing_reason='subscription_cycle'
            )
            db.session.add(txn)
            db.session.flush()

            # Credit creator
            if creator:
                if creator.balance is None:
                    creator.balance = 0
                creator.balance += txn.net_amount
                if creator.total_earned is None:
                    creator.total_earned = 0
                creator.total_earned += txn.net_amount

            db.session.commit()

            logger.info(f"Subscription {subscription.id} renewed until {subscription.end_date}")

            # Notify user about renewal
            group_name_safe = group.name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            notify_user_via_bot(
                subscription.telegram_user_id,
                f"<b>Assinatura renovada!</b>\n\n"
                f"Grupo: <b>{group_name_safe}</b>\n"
                f"Nova validade: <code>{_fmt_date_brt(subscription.end_date)}</code>\n"
                f"Valor: <code>R$ {amount_paid:.2f}</code>"
            )
        else:
            logger.info(f"Unhandled billing_reason: {billing_reason}")

    except Exception as e:
        logger.error(f"Error processing invoice.paid: {e}")
        db.session.rollback()


def handle_invoice_payment_failed(invoice):
    """Handle invoice.payment_failed — notify user with progressive warning"""
    logger.info(f"=== INVOICE PAYMENT FAILED ===")
    stripe_sub_id = invoice.get('subscription')
    stripe_invoice_id = invoice.get('id')
    attempt_count = invoice.get('attempt_count', 1)
    next_attempt = invoice.get('next_payment_attempt')  # unix timestamp or None

    if not stripe_sub_id:
        return

    try:
        subscription = Subscription.query.filter_by(
            stripe_subscription_id=stripe_sub_id
        ).first()

        if not subscription:
            logger.warning(f"No subscription found for stripe_sub_id={stripe_sub_id}")
            return

        group = subscription.group
        payment_type = subscription.payment_method_type or 'card'

        group_name_safe = group.name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        # Link for user to update payment method / pay invoice
        payment_url = invoice.get('hosted_invoice_url')
        keyboard = None

        if payment_type == 'boleto':
            if next_attempt:
                # Stripe will generate a new boleto
                msg = (
                    f"<b>Boleto expirado</b>\n\n"
                    f"O boleto da sua assinatura de <b>{group_name_safe}</b> expirou.\n"
                    f"Um novo boleto será gerado automaticamente."
                )
                btn_text = 'Ver Novo Boleto'
            else:
                # No more retries — this was the only boleto
                msg = (
                    f"<b>Boleto expirado</b>\n\n"
                    f"O boleto da sua assinatura de <b>{group_name_safe}</b> "
                    f"expirou sem pagamento.\n\n"
                    f"Sua assinatura será cancelada e você será "
                    f"removido do grupo em breve."
                )
                btn_text = 'Pagar Agora'

            if payment_url:
                keyboard = {'inline_keyboard': [[
                    {'text': btn_text, 'url': payment_url}
                ]]}
        else:
            # Progressive warning based on attempt count
            max_retries = 3

            if next_attempt:
                # There will be another retry
                remaining = max_retries - attempt_count
                msg = (
                    f"<b>Falha no pagamento</b> "
                    f"(tentativa {attempt_count}/{max_retries})\n\n"
                    f"A cobrança da assinatura de <b>{group_name_safe}</b> falhou.\n\n"
                    f"Restam <code>{remaining}</code> tentativa(s). "
                    f"Atualize seu cartão para evitar a remoção do grupo."
                )
            else:
                # Last attempt failed, no more retries
                msg = (
                    f"<b>Última tentativa de pagamento falhou</b>\n\n"
                    f"A cobrança da assinatura de <b>{group_name_safe}</b> falhou "
                    f"após {attempt_count} tentativa(s).\n\n"
                    f"Sua assinatura será cancelada e você será "
                    f"removido do grupo em breve."
                )

            if payment_url:
                keyboard = {'inline_keyboard': [[
                    {'text': 'Atualizar Pagamento', 'url': payment_url}
                ]]}

        notify_user_via_bot(subscription.telegram_user_id, msg, keyboard=keyboard)

        logger.info(
            f"User {subscription.telegram_user_id} notified about payment failure "
            f"(attempt {attempt_count}, next_attempt={'yes' if next_attempt else 'none'})"
        )

    except Exception as e:
        logger.error(f"Error handling invoice.payment_failed: {e}")


def handle_subscription_deleted(stripe_subscription):
    """Handle customer.subscription.deleted — subscription fully cancelled or payment exhausted"""
    logger.info(f"=== SUBSCRIPTION DELETED ===")
    stripe_sub_id = stripe_subscription.get('id')
    cancel_at_period_end = stripe_subscription.get('cancel_at_period_end', False)

    if not stripe_sub_id:
        return

    try:
        subscription = Subscription.query.filter_by(
            stripe_subscription_id=stripe_sub_id
        ).first()

        if not subscription:
            logger.warning(f"No subscription found for stripe_sub_id={stripe_sub_id}")
            return

        group = subscription.group

        # Determine final status
        if subscription.cancel_at_period_end:
            subscription.status = 'cancelled'
            reason_text = "Você optou por cancelar a renovação."
        else:
            subscription.status = 'expired'
            reason_text = "O pagamento não foi processado."

        subscription.auto_renew = False
        db.session.commit()

        logger.info(f"Subscription {subscription.id} set to {subscription.status}")

        # Remove user from group via bot
        remove_user_from_group_via_bot(subscription)

        group_name_safe = group.name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        # Notify user
        notify_user_via_bot(
            subscription.telegram_user_id,
            f"<b>Assinatura encerrada</b>\n\n"
            f"Sua assinatura de <b>{group_name_safe}</b> foi encerrada.\n"
            f"{reason_text}\n\n"
            f"Para assinar novamente, use o link de convite do grupo."
        )

    except Exception as e:
        logger.error(f"Error handling subscription.deleted: {e}")
        db.session.rollback()


def remove_user_from_group_via_bot(subscription):
    """Remove user from Telegram group using Bot API (respects whitelist and admins)"""
    bot_token = os.getenv('BOT_TOKEN') or os.getenv('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        logger.error("Bot token not configured for group removal")
        return

    group = subscription.group
    if not group or not group.telegram_id:
        return

    user_id_str = subscription.telegram_user_id

    # Check whitelist
    if group.is_whitelisted(user_id_str):
        logger.info(f"User {user_id_str} is whitelisted in group {group.telegram_id} — not removing")
        return

    try:
        user_id = int(user_id_str)
        chat_id = int(group.telegram_id)

        # Check if user is admin before kicking
        try:
            check_url = f"https://api.telegram.org/bot{bot_token}/getChatMember"
            resp = requests.post(check_url, json={'chat_id': chat_id, 'user_id': user_id}, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('ok') and data['result'].get('status') in ['administrator', 'creator']:
                    logger.info(f"User {user_id} is admin in group {chat_id} — not removing")
                    return
        except Exception:
            pass  # If check fails, proceed with removal

        # Ban then unban = kick without permanent ban
        ban_url = f"https://api.telegram.org/bot{bot_token}/banChatMember"
        requests.post(ban_url, json={'chat_id': chat_id, 'user_id': user_id})

        unban_url = f"https://api.telegram.org/bot{bot_token}/unbanChatMember"
        requests.post(unban_url, json={'chat_id': chat_id, 'user_id': user_id, 'only_if_banned': True})

        logger.info(f"User {user_id} removed from group {chat_id}")

    except Exception as e:
        logger.error(f"Error removing user from group: {e}")


def notify_user_via_bot(telegram_user_id, text, keyboard=None):
    """Send a Telegram message to a user via Bot API"""
    bot_token = os.getenv('BOT_TOKEN') or os.getenv('TELEGRAM_BOT_TOKEN')

    if not bot_token:
        logger.error("Bot token not configured for notifications")
        return

    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            'chat_id': str(telegram_user_id),
            'text': text,
            'parse_mode': 'HTML'
        }

        if keyboard:
            payload['reply_markup'] = keyboard

        response = requests.post(url, json=payload)

        if response.status_code == 200:
            logger.info(f"User {telegram_user_id} notified successfully")
        else:
            logger.error(f"Failed to notify user {telegram_user_id}: {response.text}")

    except Exception as e:
        logger.error(f"Error notifying user via bot: {e}")


@bp.route('/telegram', methods=['POST'])
def telegram_webhook():
    """Webhook para receber atualizações do Telegram"""
    # Verify X-Telegram-Bot-Api-Secret-Token header
    webhook_secret = os.getenv('TELEGRAM_WEBHOOK_SECRET')
    if webhook_secret:
        token_header = request.headers.get('X-Telegram-Bot-Api-Secret-Token', '')
        if not token_header or token_header != webhook_secret:
            logger.warning("Telegram webhook: invalid or missing secret token")
            return jsonify({'error': 'Forbidden'}), 403
    else:
        logger.warning("TELEGRAM_WEBHOOK_SECRET not configured — rejecting request")
        return jsonify({'error': 'Webhook secret not configured'}), 403

    # Este webhook pode ser usado futuramente para receber updates do bot
    return jsonify({'status': 'ok'}), 200