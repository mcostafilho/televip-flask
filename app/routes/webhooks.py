"""
Webhooks para processar notificações de pagamento do Stripe
"""
from flask import Blueprint, request, jsonify
import stripe
import os
import logging
import requests
from datetime import datetime
from app import db
from app.models import Transaction, Subscription, Creator, Group

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
        
    elif event['type'] == 'charge.dispute.created':
        dispute = event['data']['object']
        handle_dispute_created(dispute)
    
    return jsonify({'status': 'success'}), 200


def handle_checkout_session_completed(session):
    """Processar checkout completo - VERSÃO CORRIGIDA"""
    logger.info(f"=== PROCESSANDO CHECKOUT SESSION COMPLETO ===")
    logger.info(f"Session ID: {session['id']}")
    logger.info(f"Payment Intent: {session.get('payment_intent')}")
    logger.info(f"Payment status: {session.get('payment_status')}")
    logger.info(f"Customer email: {session.get('customer_email')}")
    logger.info(f"Metadata: {session.get('metadata')}")
    
    # Verificar se o pagamento foi realmente completado
    if session.get('payment_status') != 'paid':
        logger.warning(f"Pagamento não está pago. Status: {session.get('payment_status')}")
        return
    
    try:
        # Buscar metadados
        metadata = session.get('metadata', {})
        if not metadata:
            logger.error("Metadata vazio no checkout session")
            return
            
        transaction_id = metadata.get('transaction_id')
        subscription_id = metadata.get('subscription_id')
        
        logger.info(f"Transaction ID: {transaction_id}")
        logger.info(f"Subscription ID: {subscription_id}")
        
        if not transaction_id:
            logger.error("Transaction ID não encontrado nos metadados")
            return
        
        # Buscar a transação
        transaction = Transaction.query.filter_by(
            id=int(transaction_id),
            status='pending'
        ).first()
        
        if not transaction:
            logger.error(f"Transação {transaction_id} não encontrada ou já processada")
            return
        
        # Atualizar transação
        transaction.status = 'completed'
        transaction.stripe_payment_intent_id = session.get('payment_intent')
        transaction.paid_at = datetime.utcnow()
        
        # Buscar assinatura
        subscription = transaction.subscription
        if not subscription:
            logger.error("Assinatura não encontrada para a transação")
            return
        
        # Ativar assinatura
        subscription.status = 'active'
        subscription.start_date = datetime.utcnow()
        
        # Calcular data de expiração
        if subscription.pricing_plan.duration_type == 'days':
            subscription.end_date = subscription.start_date + timedelta(
                days=subscription.pricing_plan.duration_value
            )
        elif subscription.pricing_plan.duration_type == 'months':
            # Aproximar 30 dias por mês
            subscription.end_date = subscription.start_date + timedelta(
                days=subscription.pricing_plan.duration_value * 30
            )
        
        # Atualizar saldo do criador
        group = subscription.group
        creator = group.creator
        
        # CORREÇÃO: Adicionar indentação correta aqui (linha 120-122)
        if creator:
            # Garantir que available_balance não seja None
            if hasattr(creator, 'available_balance'):
                if creator.available_balance is None:
                    creator.available_balance = 0
                creator.available_balance += transaction.net_amount
            else:
                creator.available_balance = transaction.net_amount
                
            # Atualizar total ganho
            if hasattr(creator, 'total_earned'):
                if creator.total_earned is None:
                    creator.total_earned = 0
                creator.total_earned += transaction.net_amount
            else:
                creator.total_earned = transaction.net_amount
        
        # Salvar todas as alterações
        db.session.commit()
        
        logger.info(f"✅ Assinatura {subscription.id} ativada com sucesso!")
        logger.info(f"✅ Saldo do criador atualizado: R$ {creator.available_balance}")
        
        # Notificar bot via webhook interno
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
    """Processar criação de disputa"""
    logger.warning(f"Disputa criada: {dispute['id']}")
    
    # Buscar transação pelo payment intent
    payment_intent = dispute.get('payment_intent')
    if payment_intent:
        transaction = Transaction.query.filter_by(
            stripe_payment_intent_id=payment_intent
        ).first()
        
        if transaction:
            transaction.status = 'disputed'
            
            # Suspender assinatura
            if transaction.subscription:
                transaction.subscription.status = 'suspended'
            
            db.session.commit()


def notify_bot_payment_complete(subscription, transaction):
    """Notificar o bot que o pagamento foi completado"""
    bot_token = os.getenv('BOT_TOKEN') or os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not bot_token:
        logger.error("Bot token não configurado")
        return
    
    try:
        # URL da API do Telegram
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        
        # Mensagem para o usuário
        text = f"""
✅ **Pagamento Aprovado!**

Sua assinatura do grupo **{subscription.group.name}** foi ativada com sucesso!

📅 Válida até: {subscription.end_date.strftime('%d/%m/%Y')}
💰 Valor pago: R$ {transaction.amount:.2f}

Use o link abaixo para acessar o grupo:
{subscription.group.invite_link}

_Obrigado por assinar!_
"""
        
        # Enviar mensagem
        response = requests.post(url, json={
            'chat_id': subscription.telegram_user_id,
            'text': text,
            'parse_mode': 'Markdown'
        })
        
        if response.status_code == 200:
            logger.info(f"Usuário {subscription.telegram_user_id} notificado do pagamento")
        else:
            logger.error(f"Erro ao notificar usuário: {response.text}")
            
    except Exception as e:
        logger.error(f"Erro ao notificar bot: {str(e)}")


@bp.route('/telegram', methods=['POST'])
def telegram_webhook():
    """Webhook para receber atualizações do Telegram"""
    # Este webhook pode ser usado futuramente para receber updates do bot
    return jsonify({'status': 'ok'}), 200