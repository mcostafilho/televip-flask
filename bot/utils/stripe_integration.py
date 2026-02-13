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


def get_or_create_stripe_customer(telegram_user_id: str, username: Optional[str] = None) -> str:
    """
    Get existing Stripe customer or create new one for a Telegram user.
    Searches existing subscriptions first to reuse customer ID.

    Returns:
        stripe_customer_id
    """
    try:
        # Try to find existing customer from previous subscriptions
        from bot.utils.database import get_db_session
        from app.models import Subscription

        with get_db_session() as session:
            existing = session.query(Subscription).filter(
                Subscription.telegram_user_id == str(telegram_user_id),
                Subscription.stripe_customer_id.isnot(None)
            ).first()

            if existing and existing.stripe_customer_id:
                logger.info(f"Reusing Stripe customer {existing.stripe_customer_id} for user {telegram_user_id}")
                return existing.stripe_customer_id

        # Create new customer
        customer = stripe.Customer.create(
            metadata={
                'telegram_user_id': str(telegram_user_id),
                'telegram_username': username or ''
            },
            name=f"@{username}" if username else f"Telegram User {telegram_user_id}"
        )

        logger.info(f"Created Stripe customer {customer.id} for user {telegram_user_id}")
        return customer.id

    except stripe.error.StripeError as e:
        logger.error(f"Stripe error creating customer: {e}")
        raise
    except Exception as e:
        logger.error(f"Error creating Stripe customer: {e}")
        raise


def get_or_create_stripe_price(plan, group) -> str:
    """
    Get existing Stripe Price or create Product + Price for a plan.

    Args:
        plan: PricingPlan model instance
        group: Group model instance

    Returns:
        stripe_price_id
    """
    try:
        if plan.stripe_price_id:
            logger.info(f"Reusing Stripe price {plan.stripe_price_id} for plan {plan.id}")
            return plan.stripe_price_id

        # Create Stripe Product
        product_id = plan.stripe_product_id
        if not product_id:
            product = stripe.Product.create(
                name=f"{group.name} - {plan.name}",
                metadata={
                    'group_id': str(group.id),
                    'plan_id': str(plan.id)
                }
            )
            product_id = product.id
            logger.info(f"Created Stripe product {product_id}")

        is_lifetime = getattr(plan, 'is_lifetime', False) or plan.duration_days == 0

        if is_lifetime:
            # One-time price for lifetime plans (no recurring)
            price = stripe.Price.create(
                product=product_id,
                unit_amount=int(float(plan.price) * 100),
                currency='brl'
            )
            logger.info(f"Created one-time Stripe price {price.id} for lifetime plan {plan.id}")
        else:
            # Map duration_days to Stripe recurring interval
            days = plan.duration_days
            if days == 7:
                interval = 'week'
                interval_count = 1
            elif days == 30:
                interval = 'month'
                interval_count = 1
            elif days == 90:
                interval = 'month'
                interval_count = 3
            elif days == 180:
                interval = 'month'
                interval_count = 6
            elif days == 365:
                interval = 'year'
                interval_count = 1
            else:
                interval = 'day'
                interval_count = days

            # Create recurring Price
            price = stripe.Price.create(
                product=product_id,
                unit_amount=int(float(plan.price) * 100),  # cents
                currency='brl',
                recurring={
                    'interval': interval,
                    'interval_count': interval_count
                }
            )
            logger.info(f"Created Stripe price {price.id} for plan {plan.id}")

        # Store IDs on plan (caller must commit)
        from bot.utils.database import get_db_session
        with get_db_session() as session:
            from app.models import PricingPlan
            db_plan = session.query(PricingPlan).get(plan.id)
            if db_plan:
                db_plan.stripe_product_id = product_id
                db_plan.stripe_price_id = price.id
                session.commit()

        return price.id

    except stripe.error.StripeError as e:
        logger.error(f"Stripe error creating price: {e}")
        raise
    except Exception as e:
        logger.error(f"Error creating Stripe price: {e}")
        raise


async def create_subscription_checkout(
    customer_id: str,
    price_id: str,
    metadata: Dict,
    success_url: str,
    cancel_url: str,
    trial_end: Optional[int] = None
) -> Dict:
    """
    Create a Stripe Checkout Session in subscription mode.

    Args:
        trial_end: Unix timestamp — delays first charge until this date (plan change)

    Returns:
        Dict with success, session_id, url
    """
    try:
        # Só cartão quando: troca de plano (trial_end) ou plano curto (card_only)
        card_only = trial_end or metadata.get('card_only') == 'true'
        payment_methods = ['card'] if card_only else ['card', 'boleto']

        params = dict(
            mode='subscription',
            customer=customer_id,
            line_items=[{
                'price': price_id,
                'quantity': 1
            }],
            payment_method_types=payment_methods,
            metadata=metadata,
            success_url=success_url,
            cancel_url=cancel_url,
            locale='pt-BR'
        )

        if trial_end:
            params['subscription_data'] = {'trial_end': trial_end}

        session = stripe.checkout.Session.create(**params)

        logger.info(f"Created subscription checkout session {session.id}")

        return {
            'success': True,
            'session_id': session.id,
            'url': session.url
        }

    except stripe.error.StripeError as e:
        logger.error(f"Stripe error creating subscription checkout: {e}")
        return {
            'success': False,
            'error': str(e.user_message if hasattr(e, 'user_message') else e)
        }
    except Exception as e:
        logger.error(f"Error creating subscription checkout: {e}")
        return {
            'success': False,
            'error': 'Erro ao processar pagamento. Tente novamente.'
        }


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
            payment_method_types=['card', 'boleto'],
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
                # 'paid' = pagamento imediato, 'no_payment_required' = trial/troca de plano
                return session.payment_status in ('paid', 'no_payment_required')
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


async def get_stripe_session_details(session_id: str) -> Dict:
    """
    Retrieve Stripe Checkout Session details including subscription ID.

    Returns:
        Dict with subscription_id, payment_intent_id, payment_method_type
    """
    result = {
        'subscription_id': None,
        'payment_intent_id': None,
        'payment_method_type': None,
    }
    try:
        if not session_id or not session_id.startswith('cs_'):
            return result
        session = stripe.checkout.Session.retrieve(session_id, expand=['payment_intent'])
        result['subscription_id'] = session.get('subscription')
        if session.payment_intent:
            result['payment_intent_id'] = session.payment_intent.id
            if hasattr(session.payment_intent, 'payment_method_types') and session.payment_intent.payment_method_types:
                result['payment_method_type'] = session.payment_intent.payment_method_types[0]
        return result
    except Exception as e:
        logger.error(f"Error fetching session details: {e}")
        return result


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