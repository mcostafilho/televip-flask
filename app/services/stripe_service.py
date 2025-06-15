"""
Serviço de integração com Stripe para pagamentos
"""
import os
import stripe
from datetime import datetime
from typing import Dict, Optional
from app import db
from app.models import Transaction, Subscription, Creator

# Configurar Stripe com a chave da API
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

class StripeService:
    """Serviço para gerenciar pagamentos via Stripe"""
    
    @staticmethod
    def create_payment_intent(amount: float, metadata: dict) -> Dict:
        """Criar uma intenção de pagamento"""
        try:
            # Verificar se a API key está configurada
            if not stripe.api_key:
                return {
                    'success': False,
                    'error': 'Stripe API key não configurada'
                }
                
            intent = stripe.PaymentIntent.create(
                amount=int(amount * 100),  # Stripe usa centavos
                currency='brl',
                metadata=metadata,
                automatic_payment_methods={
                    'enabled': True,
                },
            )
            
            return {
                'success': True,
                'client_secret': intent.client_secret,
                'payment_intent_id': intent.id
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    @staticmethod
    def create_checkout_session(
        plan_name: str,
        amount: float,
        success_url: str,
        cancel_url: str,
        metadata: dict
    ) -> Dict:
        """Criar sessão de checkout"""
        try:
            # Verificar se a API key está configurada
            if not stripe.api_key:
                return {
                    'success': False,
                    'error': 'Stripe API key não configurada. Configure STRIPE_SECRET_KEY no .env'
                }
            
            # Criar sessão usando stripe.checkout.Session
            session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[{
                    'price_data': {
                        'currency': 'brl',
                        'product_data': {
                            'name': plan_name,
                            'description': f'Assinatura: {plan_name}'
                        },
                        'unit_amount': int(amount * 100),  # Converter para centavos
                    },
                    'quantity': 1,
                }],
                mode='payment',
                success_url=success_url,
                cancel_url=cancel_url,
                metadata=metadata
            )
            
            return {
                'success': True,
                'session_id': session.id,
                'url': session.url
            }
        except stripe.error.StripeError as e:
            # Erros específicos do Stripe
            error_message = str(e)
            if hasattr(e, 'user_message'):
                error_message = e.user_message
            
            return {
                'success': False,
                'error': f'Erro Stripe: {error_message}'
            }
        except Exception as e:
            # Outros erros
            return {
                'success': False,
                'error': f'Erro ao criar sessão: {str(e)}'
            }
    
    @staticmethod
    def verify_webhook_signature(payload: bytes, signature: str) -> bool:
        """Verificar assinatura do webhook"""
        try:
            webhook_secret = os.getenv('STRIPE_WEBHOOK_SECRET')
            if not webhook_secret:
                print("AVISO: STRIPE_WEBHOOK_SECRET não configurado")
                return False
                
            stripe.Webhook.construct_event(
                payload, signature, webhook_secret
            )
            return True
        except:
            return False
    
    @staticmethod
    def handle_payment_success(payment_intent_id: str) -> bool:
        """Processar pagamento bem-sucedido"""
        try:
            # Buscar payment intent
            intent = stripe.PaymentIntent.retrieve(payment_intent_id)
            
            if intent.status != 'succeeded':
                return False
            
            # Extrair metadata
            metadata = intent.metadata
            subscription_id = metadata.get('subscription_id')
            
            if not subscription_id:
                return False
            
            # Atualizar transação
            transaction = Transaction.query.filter_by(
                stripe_payment_intent_id=payment_intent_id
            ).first()
            
            if transaction:
                transaction.status = 'completed'
                transaction.paid_at = datetime.utcnow()
                
                # Ativar assinatura
                subscription = Subscription.query.get(subscription_id)
                if subscription:
                    subscription.status = 'active'
                    subscription.stripe_subscription_id = payment_intent_id
                    
                    # Atualizar saldo do criador
                    from app.models import Group
                    creator = Creator.query.join(
                        Group
                    ).filter(
                        Group.id == subscription.group_id
                    ).first()
                    
                    if creator:
                        creator.balance += transaction.net_amount
                        creator.total_earned += transaction.net_amount
                
                db.session.commit()
                return True
                
        except Exception as e:
            print(f"Erro ao processar pagamento: {e}")
            
        return False
    
    @staticmethod
    def create_subscription(
        customer_id: str,
        price_id: str,
        metadata: dict
    ) -> Dict:
        """Criar assinatura recorrente (para planos futuros)"""
        try:
            subscription = stripe.Subscription.create(
                customer=customer_id,
                items=[{
                    'price': price_id,
                }],
                metadata=metadata
            )
            
            return {
                'success': True,
                'subscription_id': subscription.id,
                'status': subscription.status
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    @staticmethod
    def cancel_subscription(subscription_id: str) -> bool:
        """Cancelar assinatura"""
        try:
            stripe.Subscription.cancel(subscription_id)
            return True
        except:
            return False
    
    @staticmethod
    def test_connection() -> Dict:
        """Testar conexão com Stripe"""
        try:
            if not stripe.api_key:
                return {
                    'success': False,
                    'error': 'API key não configurada'
                }
            
            # Tentar listar um produto para testar a conexão
            stripe.Product.list(limit=1)
            
            return {
                'success': True,
                'message': 'Conexão com Stripe OK'
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }