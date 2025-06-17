"""
Integração com Stripe para o bot
"""
import os
import stripe
from typing import Dict

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
        
        return {
            'success': True,
            'session_id': session.id,
            'url': session.url
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

async def verify_payment(session_id: str) -> bool:
    """Verificar se pagamento foi completado"""
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        return session.payment_status == 'paid'
    except:
        return False
