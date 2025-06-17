# app/routes/webhooks.py
from flask import Blueprint, request, jsonify
import stripe
import os
import logging
import requests
from app import db
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
    """Processar sessão de checkout completa - VERSÃO CORRIGIDA"""
    logger.info(f"=== PROCESSANDO CHECKOUT SESSION ===")
    logger.info(f"Session ID: {session['id']}")
    logger.info(f"Payment status: {session.get('payment_status')}")
    
    # Buscar transação usando múltiplas estratégias
    transaction = None
    
    # 1. Tentar buscar por stripe_session_id
    transaction = Transaction.query.filter_by(
        stripe_session_id=session['id']
    ).first()
    
    if not transaction:
        # 2. Tentar buscar por payment_id
        transaction = Transaction.query.filter_by(
            payment_id=session['id']
        ).first()
    
    if not transaction:
        # 3. Tentar buscar por payment_intent_id
        payment_intent_id = session.get('payment_intent')
        if payment_intent_id:
            transaction = Transaction.query.filter_by(
                stripe_payment_intent_id=payment_intent_id
            ).first()
    
    if not transaction:
        # 4. Última tentativa - buscar transação pendente recente
        # Pegar metadata do session se disponível
        metadata = session.get('metadata', {})
        user_id = metadata.get('user_id')
        
        if user_id:
            # Buscar por usuário e status pendente
            from sqlalchemy import and_, desc
            transaction = Transaction.query.join(
                Subscription
            ).filter(
                and_(
                    Subscription.telegram_user_id == user_id,
                    Transaction.status == 'pending',
                    Transaction.created_at >= datetime.utcnow() - timedelta(hours=1)
                )
            ).order_by(desc(Transaction.created_at)).first()
    
    if not transaction:
        logger.error(f"Transação não encontrada para session: {session['id']}")
        logger.error(f"Metadata: {session.get('metadata', {})}")
        return
    
    logger.info(f"Transação encontrada: ID={transaction.id}")
    
    # Verificar se já foi processada
    if transaction.status == 'completed':
        logger.info(f"Transação {transaction.id} já foi processada")
        return
    
    # Valor em centavos para reais
    amount = session.get('amount_total', 0) / 100
    
    # Atualizar transação
    transaction.status = 'completed'
    transaction.paid_at = datetime.utcnow()
    transaction.stripe_payment_intent_id = session.get('payment_intent')
    transaction.amount = amount
    
    # Recalcular taxas se necessário
    if hasattr(transaction, 'calculate_fees'):
        transaction.calculate_fees()
    
    # Ativar assinatura
    subscription = Subscription.query.get(transaction.subscription_id)
    if subscription:
        logger.info(f"Ativando assinatura {subscription.id}")
        subscription.status = 'active'
        subscription.stripe_subscription_id = session['id']
        
        # Atualizar saldo do criador
        group = Group.query.get(subscription.group_id)
        if group:
            creator = Creator.query.get(group.creator_id)
            if creator:
                # Garantir que os valores existem
                creator.balance = creator.balance or 0
                creator.available_balance = creator.available_balance or 0
                creator.total_earned = creator.total_earned or 0
                
                # Adicionar valor líquido
                net_amount = transaction.net_amount or (amount - 0.99 - (amount * 0.0799))
                creator.balance += net_amount
                creator.available_balance += net_amount
                creator.total_earned += net_amount
                
                logger.info(f"Creator {creator.id} balance updated: +R$ {net_amount:.2f}")
    
    # Commit das mudanças
    try:
        db.session.commit()
        logger.info(f"✅ Pagamento processado com sucesso para transação {transaction.id}")
        
        # Notificar via Telegram
        if subscription:
            notify_payment_success(subscription, transaction)
            
    except Exception as e:
        logger.error(f"Erro ao salvar mudanças: {e}")
        db.session.rollback()
        raise

def handle_payment_intent_succeeded(payment_intent):
    """Processar payment intent bem-sucedido"""
    logger.info(f"Payment intent succeeded: {payment_intent['id']}")
    
    # Buscar transação pelo ID do payment intent
    transaction = Transaction.query.filter_by(
        stripe_payment_intent_id=payment_intent['id']
    ).first()
    
    if not transaction:
        # Tentar buscar por payment_id
        transaction = Transaction.query.filter_by(
            payment_id=payment_intent['id']
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
                    creator.balance = creator.balance or 0
                    creator.available_balance = creator.available_balance or 0
                    creator.total_earned = creator.total_earned or 0
                    
                    creator.balance += transaction.net_amount
                    creator.available_balance += transaction.net_amount
                    creator.total_earned += transaction.net_amount
        
        db.session.commit()
        
        if subscription:
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
            logger.error("TELEGRAM_BOT_TOKEN não configurado")
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
        
        # Mensagem para o criador
        if hasattr(transaction, 'get_fee_breakdown'):
            breakdown = transaction.get_fee_breakdown()
            fee_details = f"""
💵 **Detalhamento:**
• Valor pago: {breakdown['gross']}
• Taxa fixa: {breakdown['fixed_fee']}
• Taxa %: {breakdown['percentage_fee']}
• Total de taxas: {breakdown['total_fee']}
• **Você recebe: {breakdown['net']}**
"""
        else:
            fee_details = f"""
💵 **Detalhamento:**
• Valor pago: R$ {transaction.amount:.2f}
• Taxa total: R$ {transaction.total_fee or (transaction.amount * 0.0799 + 0.99):.2f}
• **Você recebe: R$ {transaction.net_amount:.2f}**
"""
        
        message = f"""
💰 **Novo Pagamento Recebido!**

👤 Usuário: @{display_username}
📱 Grupo: {group.name}
📋 Plano: {plan.name}

{fee_details}

📊 Total de assinantes: {group.total_subscribers}
💰 Saldo disponível: R$ {creator.available_balance or creator.balance:.2f}
"""
        
        # Enviar mensagem para o criador
        requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={
                "chat_id": creator.telegram_id,
                "text": message,
                "parse_mode": "Markdown"
            }
        )
        
        # Notificar usuário também
        user_message = f"""
✅ **Pagamento Confirmado!**

Sua assinatura para o grupo **{group.name}** está ativa!

📋 Plano: {plan.name}
📅 Válido até: {subscription.end_date.strftime('%d/%m/%Y')}

Use /start para ver o link de acesso ao grupo.
"""
        
        requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={
                "chat_id": subscription.telegram_user_id,
                "text": user_message,
                "parse_mode": "Markdown"
            }
        )
        
    except Exception as e:
        logger.error(f"Erro ao notificar pagamento: {e}")

# Importar timedelta se necessário
from datetime import timedelta