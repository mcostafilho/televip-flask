# bot/utils/stripe_integration.py
"""
Integração com Stripe para o bot - VERSÃO CORRIGIDA
"""
import os
import stripe
import logging
from typing import Dict

logger = logging.getLogger(__name__)
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

async def create_checkout_session(
    amount: float,
    group_name: str,
    plan_name: str,
    user_id: str,
    success_url: str,
    cancel_url: str
) -> Dict:
    """Criar sessão de checkout no Stripe"""
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'brl',
                    'product_data': {
                        'name': f'{group_name} - {plan_name}',
                        'description': f'Assinatura do grupo {group_name}'
                    },
                    'unit_amount': int(amount * 100),  # Stripe usa centavos
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                'user_id': user_id,
                'group_name': group_name,
                'plan_name': plan_name
            }
        )
        
        logger.info(f"Sessão Stripe criada: {session.id}")
        
        return {
            'success': True,
            'session_id': session.id,
            'url': session.url
        }
        
    except Exception as e:
        logger.error(f"Erro ao criar sessão Stripe: {e}")
        return {
            'success': False,
            'error': str(e)
        }

async def verify_payment(payment_id: str) -> bool:
    """Verificar se pagamento foi completado - VERSÃO MELHORADA"""
    try:
        logger.info(f"Verificando pagamento: {payment_id}")
        
        # Tentar como checkout session primeiro
        try:
            session = stripe.checkout.Session.retrieve(payment_id)
            logger.info(f"Session encontrada: status={session.payment_status}")
            return session.payment_status == 'paid'
        except stripe.error.InvalidRequestError:
            logger.info("Não é uma session, tentando como payment intent...")
            pass
        
        # Tentar como payment intent
        try:
            intent = stripe.PaymentIntent.retrieve(payment_id)
            logger.info(f"Payment intent encontrado: status={intent.status}")
            return intent.status == 'succeeded'
        except stripe.error.InvalidRequestError:
            logger.info("Não é um payment intent...")
            pass
        
        # Se chegou aqui, não encontrou nada
        logger.warning(f"ID {payment_id} não encontrado no Stripe")
        return False
        
    except Exception as e:
        logger.error(f"Erro ao verificar pagamento: {e}")
        return False

async def get_payment_details(payment_id: str) -> Dict:
    """Obter detalhes do pagamento"""
    try:
        # Tentar como session
        try:
            session = stripe.checkout.Session.retrieve(payment_id)
            return {
                'success': True,
                'type': 'session',
                'status': session.payment_status,
                'amount': session.amount_total / 100,
                'currency': session.currency,
                'customer_email': session.customer_details.email if session.customer_details else None
            }
        except:
            pass
        
        # Tentar como payment intent
        try:
            intent = stripe.PaymentIntent.retrieve(payment_id)
            return {
                'success': True,
                'type': 'payment_intent',
                'status': intent.status,
                'amount': intent.amount / 100,
                'currency': intent.currency
            }
        except:
            pass
        
        return {
            'success': False,
            'error': 'Payment not found'
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

async def cancel_payment(payment_id: str) -> bool:
    """Cancelar um pagamento pendente"""
    try:
        # Tentar cancelar como payment intent
        try:
            intent = stripe.PaymentIntent.cancel(payment_id)
            return True
        except:
            pass
        
        # Não é possível cancelar uma session depois de criada
        return False
        
    except Exception as e:
        logger.error(f"Erro ao cancelar pagamento: {e}")
        return False

def test_stripe_connection() -> bool:
    """Testar conexão com Stripe"""
    try:
        # Tentar listar 1 produto para testar
        stripe.Product.list(limit=1)
        logger.info("✅ Conexão com Stripe OK")
        return True
    except Exception as e:
        logger.error(f"❌ Erro na conexão com Stripe: {e}")
        return False