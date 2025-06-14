# app/routes/webhooks.py
from flask import Blueprint, request, jsonify
import stripe
import os
from app import db
from app.services.stripe_service import StripeService
from app.models import Transaction, Subscription, Creator, Group
from datetime import datetime

bp = Blueprint('webhooks', __name__, url_prefix='/webhooks')

@bp.route('/stripe', methods=['POST'])
def stripe_webhook():
    """Processar webhooks do Stripe"""
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature')
    
    # Verificar assinatura
    if not StripeService.verify_webhook_signature(payload, sig_header):
        return jsonify({'error': 'Invalid signature'}), 400
    
    try:
        event = stripe.Event.construct_from(
            request.get_json(), stripe.api_key
        )
        
        # Processar diferentes tipos de eventos
        if event['type'] == 'payment_intent.succeeded':
            payment_intent = event['data']['object']
            handle_payment_intent_succeeded(payment_intent)
            
        elif event['type'] == 'checkout.session.completed':
            session = event['data']['object']
            handle_checkout_session_completed(session)
            
        elif event['type'] == 'payment_intent.payment_failed':
            payment_intent = event['data']['object']
            handle_payment_failed(payment_intent)
        
        return jsonify({'status': 'success'}), 200
        
    except Exception as e:
        print(f"Erro no webhook: {e}")
        return jsonify({'error': str(e)}), 400

def handle_payment_intent_succeeded(payment_intent):
    """Processar pagamento bem-sucedido"""
    metadata = payment_intent.get('metadata', {})
    subscription_id = metadata.get('subscription_id')
    
    if subscription_id:
        # Buscar e atualizar transação
        transaction = Transaction.query.filter_by(
            stripe_payment_intent_id=payment_intent['id']
        ).first()
        
        if not transaction:
            # Criar nova transação se não existir
            subscription = Subscription.query.get(subscription_id)
            if subscription:
                transaction = Transaction(
                    subscription_id=subscription_id,
                    amount=payment_intent['amount'] / 100,  # Converter de centavos
                    fee=(payment_intent['amount'] / 100) * 0.01,  # 1% de taxa
                    net_amount=(payment_intent['amount'] / 100) * 0.99,
                    status='completed',
                    payment_method='stripe',
                    stripe_payment_intent_id=payment_intent['id'],
                    paid_at=datetime.utcnow()
                )
                db.session.add(transaction)
        else:
            transaction.status = 'completed'
            transaction.paid_at = datetime.utcnow()
        
        # Ativar assinatura
        subscription = Subscription.query.get(subscription_id)
        if subscription:
            subscription.status = 'active'
            
            # Atualizar saldo do criador
            group = Group.query.get(subscription.group_id)
            if group:
                creator = Creator.query.get(group.creator_id)
                if creator:
                    creator.balance += transaction.net_amount
                    creator.total_earned += transaction.net_amount
                    
                    # Incrementar contador de assinantes
                    group.total_subscribers += 1
        
        db.session.commit()
        
        # TODO: Adicionar usuário ao grupo do Telegram via bot

def handle_checkout_session_completed(session):
    """Processar sessão de checkout completa"""
    metadata = session.get('metadata', {})
    
    # Processar pagamento similar ao payment_intent
    # Útil para pagamentos via Checkout do Stripe
    pass

def handle_payment_failed(payment_intent):
    """Processar falha no pagamento"""
    metadata = payment_intent.get('metadata', {})
    subscription_id = metadata.get('subscription_id')
    
    if subscription_id:
        transaction = Transaction.query.filter_by(
            stripe_payment_intent_id=payment_intent['id']
        ).first()
        
        if transaction:
            transaction.status = 'failed'
            db.session.commit()

@bp.route('/telegram', methods=['POST'])
def telegram_webhook():
    """Processar webhooks do Telegram (opcional)"""
    # Implementar se quiser receber updates do Telegram via webhook
    # em vez de polling
    return jsonify({'status': 'ok'}), 200