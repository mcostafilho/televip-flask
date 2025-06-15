#!/usr/bin/env python3
"""
Script para verificar e processar pagamentos pendentes
Execute: python check_pending_payment.py
"""
import os
import sys
import stripe
from datetime import datetime
from dotenv import load_dotenv

# Adicionar path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Carregar .env
load_dotenv()

# Configurar Stripe
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

def check_pending_payments():
    """Verificar pagamentos pendentes no Stripe"""
    print("🔍 Verificando pagamentos pendentes...\n")
    
    # Importar modelos
    from app import create_app, db
    from app.models import Subscription, Transaction, Group, Creator
    
    app = create_app()
    
    with app.app_context():
        # Buscar assinaturas pendentes
        pending_subs = Subscription.query.filter_by(status='pending').all()
        
        print(f"📋 Encontradas {len(pending_subs)} assinaturas pendentes\n")
        
        for sub in pending_subs:
            print(f"🔍 Verificando assinatura ID: {sub.id}")
            print(f"   Usuário: {sub.telegram_username}")
            print(f"   Grupo: {sub.group.name}")
            print(f"   Criada em: {sub.created_at}")
            
            # Buscar transação
            transaction = Transaction.query.filter_by(
                subscription_id=sub.id
            ).first()
            
            if transaction and transaction.stripe_payment_intent_id:
                print(f"   Session ID: {transaction.stripe_payment_intent_id}")
                
                # Verificar no Stripe
                try:
                    session = stripe.checkout.Session.retrieve(
                        transaction.stripe_payment_intent_id
                    )
                    
                    print(f"   Status no Stripe: {session.payment_status}")
                    
                    if session.payment_status == 'paid':
                        print("   ✅ PAGAMENTO CONFIRMADO NO STRIPE!")
                        
                        # Processar manualmente
                        if input("   Processar pagamento? (s/n): ").lower() == 's':
                            # Atualizar transação
                            transaction.status = 'completed'
                            transaction.paid_at = datetime.utcnow()
                            
                            # Ativar assinatura
                            sub.status = 'active'
                            
                            # Atualizar saldo do criador
                            group = sub.group
                            creator = group.creator
                            
                            creator.balance += transaction.net_amount
                            creator.total_earned = (creator.total_earned or 0) + transaction.net_amount
                            
                            # Incrementar contador
                            group.total_subscribers = (group.total_subscribers or 0) + 1
                            
                            db.session.commit()
                            
                            print("   ✅ Pagamento processado com sucesso!")
                            
                            # Notificar usuário
                            if creator.telegram_id:
                                try:
                                    import requests
                                    bot_token = os.getenv('BOT_TOKEN')
                                    
                                    # Notificar criador
                                    message = f"""
💰 **Nova Assinatura!**

👤 Usuário: @{sub.telegram_username}
📱 Grupo: {group.name}
📋 Plano: {sub.plan.name}
💵 Valor: R$ {transaction.net_amount:.2f} (líquido)

Total de assinantes: {group.total_subscribers}
"""
                                    
                                    requests.post(
                                        f"https://api.telegram.org/bot{bot_token}/sendMessage",
                                        json={
                                            "chat_id": creator.telegram_id,
                                            "text": message,
                                            "parse_mode": "Markdown"
                                        }
                                    )
                                    
                                    # Notificar assinante
                                    user_message = f"""
✅ **Pagamento Confirmado!**

Sua assinatura do grupo **{group.name}** foi ativada com sucesso!

Use /status para ver os detalhes e obter o link de acesso.
"""
                                    
                                    requests.post(
                                        f"https://api.telegram.org/bot{bot_token}/sendMessage",
                                        json={
                                            "chat_id": sub.telegram_user_id,
                                            "text": user_message,
                                            "parse_mode": "Markdown"
                                        }
                                    )
                                    
                                except Exception as e:
                                    print(f"   ⚠️  Erro ao notificar: {e}")
                    else:
                        print(f"   ❌ Pagamento ainda não confirmado: {session.payment_status}")
                        
                except Exception as e:
                    print(f"   ❌ Erro ao verificar no Stripe: {e}")
            else:
                print("   ❌ Sem ID de sessão do Stripe")
            
            print()

def list_recent_stripe_sessions():
    """Listar sessões recentes do Stripe"""
    print("\n📋 Sessões recentes do Stripe:\n")
    
    try:
        sessions = stripe.checkout.Session.list(limit=10)
        
        for session in sessions.data:
            print(f"ID: {session.id}")
            print(f"Status: {session.payment_status}")
            print(f"Valor: R$ {session.amount_total / 100:.2f}")
            print(f"Criado: {datetime.fromtimestamp(session.created)}")
            if session.metadata:
                print(f"Metadata: {session.metadata}")
            print("-" * 50)
            
    except Exception as e:
        print(f"Erro ao listar sessões: {e}")

if __name__ == "__main__":
    print("=== VERIFICADOR DE PAGAMENTOS PENDENTES ===\n")
    
    # Verificar pagamentos pendentes
    check_pending_payments()
    
    # Listar sessões recentes
    if input("\nListar sessões recentes do Stripe? (s/n): ").lower() == 's':
        list_recent_stripe_sessions()
    
    print("\n✅ Verificação concluída!")