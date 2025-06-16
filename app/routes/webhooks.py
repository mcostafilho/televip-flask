# app/routes/webhooks.py
from flask import Blueprint, request, jsonify
import stripe
import os
import logging
import requests
from app import db
from app.services.stripe_service import StripeService
from app.services.payment_service import PaymentService
from app.models import Transaction, Subscription, Creator, Group
from datetime import datetime

bp = Blueprint('webhooks', __name__, url_prefix='/webhooks')
logger = logging.getLogger(__name__)

@bp.route('/stripe', methods=['POST'])
def stripe_webhook():
    """Processar webhooks do Stripe com cálculo correto de taxas"""
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
    
    # Processar diferentes tipos de eventos
    logger.info(f"Received event: {event['type']}")
    
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        handle_checkout_session_completed(session)
        
    elif event['type'] == 'payment_intent.succeeded':
        payment_intent = event['data']['object']
        handle_payment_intent_succeeded(payment_intent)
        
    elif event['type'] == 'payment_intent.payment_failed':
        payment_intent = event['data']['object']
        handle_payment_failed(payment_intent)
    
    return jsonify({'status': 'success'}), 200

def handle_checkout_session_completed(session):
    """Processar sessão de checkout completa com taxas corretas"""
    logger.info(f"=== PROCESSANDO CHECKOUT SESSION ===")
    logger.info(f"Session ID: {session['id']}")
    logger.info(f"Payment status: {session.get('payment_status')}")
    
    # Extrair metadata
    metadata = session.get('metadata', {})
    subscription_id = metadata.get('subscription_id')
    transaction_id = metadata.get('transaction_id')
    
    if not subscription_id:
        logger.error("No subscription_id in metadata")
        return
    
    # Buscar assinatura
    subscription = Subscription.query.get(subscription_id)
    if not subscription:
        logger.error(f"Subscription {subscription_id} not found")
        return
    
    # Valor em centavos para reais
    amount = session.get('amount_total', 0) / 100
    
    # Buscar ou criar transação
    if transaction_id:
        transaction = Transaction.query.get(transaction_id)
    else:
        transaction = Transaction.query.filter_by(
            subscription_id=subscription_id,
            status='pending'
        ).first()
    
    if not transaction:
        # Criar nova transação com cálculo automático de taxas
        transaction = Transaction(
            subscription_id=subscription_id,
            amount=amount,
            status='completed',
            payment_method='stripe',
            stripe_payment_intent_id=session.get('payment_intent'),
            paid_at=datetime.utcnow()
        )
        db.session.add(transaction)
    else:
        # Atualizar transação existente
        transaction.status = 'completed'
        transaction.paid_at = datetime.utcnow()
        transaction.stripe_payment_intent_id = session.get('payment_intent')
        
        # Recalcular taxas para garantir precisão
        if transaction.amount != amount:
            transaction.amount = amount
            transaction.calculate_fees()
    
    # Ativar assinatura
    subscription.status = 'active'
    subscription.stripe_subscription_id = session['id']
    
    # Atualizar saldo do criador (valor líquido)
    group = Group.query.get(subscription.group_id)
    if group:
        creator = Creator.query.get(group.creator_id)
        if creator:
            creator.balance += transaction.net_amount
            creator.total_earned += transaction.net_amount
            
            logger.info(f"Creator {creator.id} balance updated: +R$ {transaction.net_amount:.2f}")
    
    # Commit das mudanças
    db.session.commit()
    
    # Notificar via Telegram
    notify_payment_success(subscription, transaction)
    
    logger.info(f"Payment processed successfully for subscription {subscription_id}")

def handle_payment_intent_succeeded(payment_intent):
    """Processar payment intent bem-sucedido"""
    logger.info(f"Payment intent succeeded: {payment_intent['id']}")
    
    # Buscar transação pelo ID do payment intent
    transaction = Transaction.query.filter_by(
        stripe_payment_intent_id=payment_intent['id']
    ).first()
    
    if transaction and transaction.status != 'completed':
        transaction.status = 'completed'
        transaction.paid_at = datetime.utcnow()
        
        # Ativar assinatura
        subscription = Subscription.query.get(transaction.subscription_id)
        if subscription:
            subscription.status = 'active'
            
            # Atualizar saldo do criador
            group = Group.query.get(subscription.group_id)
            if group:
                creator = Creator.query.get(group.creator_id)
                if creator:
                    creator.balance += transaction.net_amount
                    creator.total_earned += transaction.net_amount
        
        db.session.commit()
        notify_payment_success(subscription, transaction)

def handle_payment_failed(payment_intent):
    """Processar falha no pagamento"""
    metadata = payment_intent.get('metadata', {})
    subscription_id = metadata.get('subscription_id')
    
    if subscription_id:
        transaction = Transaction.query.filter_by(
            subscription_id=subscription_id,
            stripe_payment_intent_id=payment_intent['id']
        ).first()
        
        if transaction:
            transaction.status = 'failed'
            db.session.commit()
            
    logger.info(f"Payment failed for intent: {payment_intent['id']}")

def notify_payment_success(subscription, transaction):
    """Notificar sucesso do pagamento com detalhes das taxas"""
    try:
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not bot_token:
            return
        
        # Buscar informações
        group = Group.query.get(subscription.group_id)
        creator = Creator.query.get(group.creator_id)
        plan = subscription.plan
        
        # Obter username do Telegram
        user_response = requests.get(
            f"https://api.telegram.org/bot{bot_token}/getChat",
            params={"chat_id": subscription.telegram_user_id}
        )
        
        display_username = subscription.telegram_username
        if user_response.status_code == 200:
            user_data = user_response.json().get('result', {})
            display_username = user_data.get('username', subscription.telegram_username)
        
        # Mensagem para o criador com breakdown das taxas
        breakdown = transaction.get_fee_breakdown()
        message = f"""
💰 **Novo Pagamento Recebido!**

👤 Usuário: @{display_username}
📱 Grupo: {group.name}
📋 Plano: {plan.name}

💵 **Detalhamento:**
• Valor pago: {breakdown['gross']}
• Taxa fixa: {breakdown['fixed_fee']}
• Taxa %: {breakdown['percentage_fee']}
• Total de taxas: {breakdown['total_fee']}
• **Você recebe: {breakdown['net']}**

📊 Total de assinantes: {group.total_subscribers}
💰 Saldo disponível: R$ {creator.balance:.2f}
"""
        
        requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={
                "chat_id": creator.telegram_id,
                "text": message,
                "parse_mode": "Markdown"
            }
        )
        
        # Enviar botão para o usuário entrar no grupo
        user_message = f"""
✅ **Pagamento Confirmado!**

Valor pago: R$ {transaction.amount:.2f}
Taxa de processamento: R$ {transaction.total_fee:.2f}

Clique no botão abaixo para entrar no grupo VIP:
"""
        
        keyboard = {
            "inline_keyboard": [[{
                "text": "🚀 ENTRAR NO GRUPO VIP",
                "url": f"https://t.me/{os.getenv('BOT_USERNAME')}?start=success_{subscription.id}"
            }]]
        }
        
        requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={
                "chat_id": subscription.telegram_user_id,
                "text": user_message,
                "parse_mode": "Markdown",
                "reply_markup": keyboard
            }
        )
        
    except Exception as e:
        logger.error(f"Error notifying: {e}")

@bp.route('/pix', methods=['POST'])
def pix_webhook():
    """Webhook para processar notificações de pagamento PIX"""
    # Implementar quando integrar com provedor de PIX real
    # Por enquanto, retornar sucesso
    data = request.get_json()
    
    logger.info(f"PIX webhook received: {data}")
    
    # Exemplo de processamento PIX
    # transaction_id = data.get('transaction_id')
    # status = data.get('status')
    
    # if status == 'confirmed':
    #     process_pix_payment_confirmed(transaction_id)
    
    return jsonify({'status': 'ok'}), 200