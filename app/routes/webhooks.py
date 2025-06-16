# app/routes/webhooks.py - CORREÇÃO COMPLETA

from flask import Blueprint, request, jsonify
import stripe
import os
import logging
from app import db
from app.services.stripe_service import StripeService
from app.models import Transaction, Subscription, Creator, Group
from datetime import datetime

bp = Blueprint('webhooks', __name__, url_prefix='/webhooks')
logger = logging.getLogger(__name__)

@bp.route('/stripe', methods=['POST'])
def stripe_webhook():
    """Processar webhooks do Stripe"""
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
    """Processar sessão de checkout completa"""
    logger.info(f"=== PROCESSANDO CHECKOUT SESSION ===")
    logger.info(f"Session ID: {session['id']}")
    logger.info(f"Payment status: {session.get('payment_status')}")
    
    # Extrair metadata
    metadata = session.get('metadata', {})
    subscription_id = metadata.get('subscription_id')
    transaction_id = metadata.get('transaction_id')
    telegram_username = metadata.get('telegram_username', '')  # Pegar username da metadata
    user_id = metadata.get('user_id', '')
    
    logger.info(f"Metadata - subscription_id: {subscription_id}")
    logger.info(f"Metadata - transaction_id: {transaction_id}")
    logger.info(f"Metadata - telegram_username: {telegram_username}")
    logger.info(f"Metadata - user_id: {user_id}")
    
    if not subscription_id:
        logger.error("No subscription_id in metadata")
        return
    
    # Buscar e atualizar transação e assinatura
    transaction = None
    if transaction_id:
        transaction = Transaction.query.get(transaction_id)
    
    if not transaction:
        # Buscar por subscription_id
        transaction = Transaction.query.filter_by(
            subscription_id=subscription_id,
            status='pending'
        ).first()
    
    if not transaction:
        logger.error(f"Transaction not found for subscription {subscription_id}")
        return
    
    # Atualizar transação
    transaction.status = 'completed'
    transaction.paid_at = datetime.utcnow()
    transaction.stripe_payment_intent_id = session.get('payment_intent')
    
    # Ativar assinatura
    subscription = Subscription.query.get(subscription_id)
    if subscription:
        subscription.status = 'active'
        subscription.stripe_subscription_id = session['id']
        
        # IMPORTANTE: Atualizar o username se estiver na metadata
        if telegram_username and not subscription.telegram_username:
            subscription.telegram_username = telegram_username
            logger.info(f"Username atualizado para: {telegram_username}")
        
        # Atualizar saldo do criador
        group = Group.query.get(subscription.group_id)
        if group:
            creator = Creator.query.get(group.creator_id)
            if creator:
                creator.balance += transaction.net_amount
                creator.total_earned = (creator.total_earned or 0) + transaction.net_amount
                
                # Incrementar contador de assinantes
                group.total_subscribers = (group.total_subscribers or 0) + 1
                
                logger.info(f"Updated creator balance: +R$ {transaction.net_amount:.2f}")
    
    db.session.commit()
    
    # Notificar criador via Telegram (se tiver telegram_id)
    if creator and creator.telegram_id:
        try:
            import requests
            bot_token = os.getenv('BOT_TOKEN')
            
            # Usar o username correto
            display_username = subscription.telegram_username or telegram_username or 'Usuário'
            
            message = f"""
💰 **Nova Assinatura!**

👤 Usuário: @{display_username}
📱 Grupo: {group.name}
📋 Plano: {subscription.plan.name}
💵 Valor: R$ {transaction.net_amount:.2f} (líquido)

Total de assinantes: {group.total_subscribers}
Saldo disponível: R$ {creator.balance:.2f}
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

Clique no botão abaixo para entrar no grupo VIP:
"""
            
            keyboard = {
                "inline_keyboard": [[{
                    "text": "🚀 ENTRAR NO GRUPO VIP",
                    "url": f"https://t.me/{os.getenv('BOT_USERNAME')}?start=success_{subscription_id}"
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
    
    logger.info(f"Payment processed successfully for subscription {subscription_id}")

def handle_payment_intent_succeeded(payment_intent):
    """Processar payment intent bem-sucedido"""
    # Similar ao checkout.session.completed
    # Alguns pagamentos podem vir por aqui
    logger.info(f"Payment intent succeeded: {payment_intent['id']}")

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

@bp.route('/telegram', methods=['POST'])
def telegram_webhook():
    """Processar webhooks do Telegram (opcional)"""
    # Implementar se quiser receber updates do Telegram via webhook
    # em vez de polling
    return jsonify({'status': 'ok'}), 200