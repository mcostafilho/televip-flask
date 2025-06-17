"""
Integração com Stripe para o bot - VERSÃO CORRIGIDA
Handles payment processing, verification and refunds
"""
import os
import stripe
import logging
from typing import Dict, Optional, List
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Configurar Stripe
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

# Verificar se está em modo teste
IS_TEST_MODE = os.getenv('STRIPE_SECRET_KEY', '').startswith('sk_test_')


async def create_checkout_session(
    amount: float,
    group_name: str,
    plan_name: str,
    user_id: str,
    success_url: str,
    cancel_url: str,
    metadata: Optional[Dict] = None
) -> Dict:
    """
    Criar sessão de checkout no Stripe
    
    Args:
        amount: Valor em reais
        group_name: Nome do grupo
        plan_name: Nome do plano
        user_id: ID do usuário no Telegram
        success_url: URL de retorno em caso de sucesso
        cancel_url: URL de retorno em caso de cancelamento
        metadata: Dados adicionais opcionais
    
    Returns:
        Dict com sucesso, session_id e url
    """
    try:
        # Preparar metadata
        session_metadata = {
            'user_id': user_id,
            'group_name': group_name,
            'plan_name': plan_name,
            'timestamp': str(datetime.utcnow().timestamp())
        }
        
        if metadata:
            session_metadata.update(metadata)
        
        # Criar sessão de checkout
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'brl',
                    'product_data': {
                        'name': f'{group_name} - {plan_name}',
                        'description': f'Assinatura do grupo {group_name}',
                        'images': []  # Adicionar imagem do grupo se disponível
                    },
                    'unit_amount': int(amount * 100),  # Stripe usa centavos
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=success_url,
            cancel_url=cancel_url,
            metadata=session_metadata,
            expires_at=int((datetime.utcnow() + timedelta(minutes=30)).timestamp()),  # Expira em 30 minutos
            allow_promotion_codes=True,  # Permitir cupons de desconto
            locale='pt-BR'  # Interface em português
        )
        
        logger.info(f"✅ Sessão Stripe criada: {session.id}")
        logger.info(f"URL de pagamento: {session.url}")
        
        return {
            'success': True,
            'session_id': session.id,
            'url': session.url
        }
        
    except stripe.error.StripeError as e:
        logger.error(f"Erro Stripe ao criar sessão: {e}")
        return {
            'success': False,
            'error': str(e.user_message if hasattr(e, 'user_message') else e)
        }
    except Exception as e:
        logger.error(f"Erro inesperado ao criar sessão: {e}")
        return {
            'success': False,
            'error': 'Erro ao processar pagamento. Tente novamente.'
        }


async def verify_payment(payment_id: str) -> bool:
    """
    Verificar se pagamento foi completado - VERSÃO CORRIGIDA
    Funciona tanto com session_id quanto payment_intent_id
    
    Args:
        payment_id: ID da sessão ou payment intent
        
    Returns:
        True se pagamento confirmado, False caso contrário
    """
    try:
        logger.info(f"Verificando pagamento: {payment_id}")
        
        # Identificar tipo de ID pelo prefixo
        if payment_id.startswith('cs_'):
            # É um checkout session ID
            try:
                session = stripe.checkout.Session.retrieve(payment_id)
                logger.info(f"Session encontrada - Status: {session.payment_status}")
                return session.payment_status == 'paid'
            except stripe.error.InvalidRequestError:
                logger.warning(f"Session {payment_id} não encontrada")
                return False
                
        elif payment_id.startswith('pi_'):
            # É um payment intent ID
            try:
                intent = stripe.PaymentIntent.retrieve(payment_id)
                logger.info(f"Payment intent encontrado - Status: {intent.status}")
                return intent.status == 'succeeded'
            except stripe.error.InvalidRequestError:
                logger.warning(f"Payment intent {payment_id} não encontrado")
                return False
        
        else:
            logger.warning(f"ID desconhecido (não é cs_ nem pi_): {payment_id}")
            return False
        
    except Exception as e:
        logger.error(f"Erro ao verificar pagamento: {e}")
        return False


async def get_payment_details(payment_id: str) -> Dict:
    """
    Obter detalhes completos do pagamento
    
    Args:
        payment_id: ID da sessão ou payment intent
        
    Returns:
        Dict com detalhes do pagamento
    """
    try:
        result = {
            'success': False,
            'type': None,
            'status': None,
            'amount': 0,
            'currency': 'brl',
            'customer_email': None,
            'payment_method': None,
            'metadata': {}
        }
        
        # Tentar como checkout session
        if payment_id.startswith('cs_'):
            try:
                session = stripe.checkout.Session.retrieve(
                    payment_id,
                    expand=['payment_intent', 'customer']
                )
                
                result.update({
                    'success': True,
                    'type': 'checkout_session',
                    'status': session.payment_status,
                    'amount': session.amount_total / 100,
                    'currency': session.currency,
                    'customer_email': session.customer_email or (session.customer.email if session.customer else None),
                    'metadata': session.metadata,
                    'payment_intent_id': session.payment_intent.id if session.payment_intent else None
                })
                
                # Se tiver payment intent, pegar detalhes do método de pagamento
                if session.payment_intent:
                    result['payment_method'] = session.payment_intent.payment_method
                    
            except stripe.error.InvalidRequestError:
                pass
        
        # Tentar como payment intent
        elif payment_id.startswith('pi_'):
            try:
                intent = stripe.PaymentIntent.retrieve(
                    payment_id,
                    expand=['customer', 'payment_method']
                )
                
                result.update({
                    'success': True,
                    'type': 'payment_intent',
                    'status': intent.status,
                    'amount': intent.amount / 100,
                    'currency': intent.currency,
                    'customer_email': intent.customer.email if intent.customer else None,
                    'metadata': intent.metadata,
                    'payment_method': intent.payment_method.type if intent.payment_method else None
                })
                
            except stripe.error.InvalidRequestError:
                pass
        
        return result
        
    except Exception as e:
        logger.error(f"Erro ao obter detalhes do pagamento: {e}")
        return {'success': False, 'error': str(e)}


async def cancel_payment(payment_id: str) -> Dict:
    """
    Cancelar um pagamento pendente
    
    Args:
        payment_id: ID da sessão ou payment intent
        
    Returns:
        Dict com resultado da operação
    """
    try:
        if payment_id.startswith('cs_'):
            # Expirar checkout session
            session = stripe.checkout.Session.expire(payment_id)
            return {
                'success': True,
                'message': 'Sessão de pagamento cancelada'
            }
            
        elif payment_id.startswith('pi_'):
            # Cancelar payment intent
            intent = stripe.PaymentIntent.cancel(payment_id)
            return {
                'success': True,
                'message': 'Pagamento cancelado'
            }
        
        return {
            'success': False,
            'error': 'ID de pagamento inválido'
        }
        
    except stripe.error.InvalidRequestError as e:
        return {
            'success': False,
            'error': 'Pagamento não encontrado ou já processado'
        }
    except Exception as e:
        logger.error(f"Erro ao cancelar pagamento: {e}")
        return {
            'success': False,
            'error': str(e)
        }


async def create_refund(payment_intent_id: str, amount: Optional[float] = None, reason: str = 'requested_by_customer') -> Dict:
    """
    Criar reembolso para um pagamento
    
    Args:
        payment_intent_id: ID do payment intent
        amount: Valor a reembolsar (None para reembolso total)
        reason: Motivo do reembolso
        
    Returns:
        Dict com resultado da operação
    """
    try:
        refund_data = {
            'payment_intent': payment_intent_id,
            'reason': reason
        }
        
        if amount:
            refund_data['amount'] = int(amount * 100)  # Converter para centavos
        
        refund = stripe.Refund.create(**refund_data)
        
        return {
            'success': True,
            'refund_id': refund.id,
            'amount': refund.amount / 100,
            'status': refund.status
        }
        
    except stripe.error.InvalidRequestError as e:
        return {
            'success': False,
            'error': 'Pagamento não encontrado ou não pode ser reembolsado'
        }
    except Exception as e:
        logger.error(f"Erro ao criar reembolso: {e}")
        return {
            'success': False,
            'error': str(e)
        }


async def list_recent_payments(customer_email: Optional[str] = None, limit: int = 10) -> List[Dict]:
    """
    Listar pagamentos recentes
    
    Args:
        customer_email: Email do cliente (opcional)
        limit: Número máximo de resultados
        
    Returns:
        Lista de pagamentos
    """
    try:
        # Buscar payment intents
        search_params = {
            'limit': limit,
            'expand': ['data.customer']
        }
        
        if customer_email:
            # Primeiro buscar o customer
            customers = stripe.Customer.list(email=customer_email, limit=1)
            if customers.data:
                search_params['customer'] = customers.data[0].id
        
        intents = stripe.PaymentIntent.list(**search_params)
        
        payments = []
        for intent in intents.data:
            payments.append({
                'id': intent.id,
                'amount': intent.amount / 100,
                'currency': intent.currency,
                'status': intent.status,
                'created': datetime.fromtimestamp(intent.created),
                'customer_email': intent.customer.email if intent.customer else None,
                'metadata': intent.metadata
            })
        
        return payments
        
    except Exception as e:
        logger.error(f"Erro ao listar pagamentos: {e}")
        return []


# Funções auxiliares
def format_stripe_amount(amount: int, currency: str = 'brl') -> str:
    """Formatar valor do Stripe para exibição"""
    value = amount / 100
    if currency.lower() == 'brl':
        return f'R$ {value:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return f'{value:.2f} {currency.upper()}'


def validate_stripe_webhook(payload: bytes, signature: str, secret: str) -> bool:
    """Validar assinatura do webhook do Stripe"""
    try:
        stripe.Webhook.construct_event(payload, signature, secret)
        return True
    except:
        return False


# Verificar configuração ao importar
if not stripe.api_key:
    logger.warning("⚠️ STRIPE_SECRET_KEY não configurado!")
else:
    logger.info(f"✅ Stripe configurado em modo: {'TESTE' if IS_TEST_MODE else 'PRODUÇÃO'}")