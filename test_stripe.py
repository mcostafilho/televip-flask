#!/usr/bin/env python3
"""
Teste do Stripe no contexto do bot
Execute na raiz: python test_bot_stripe.py
"""
import os
import sys
from dotenv import load_dotenv

# Carregar .env
load_dotenv()

print("=== TESTE STRIPE NO CONTEXTO DO BOT ===\n")

# 1. Simular o ambiente do bot
print("1. Configurando ambiente como o bot faria:")
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 2. Testar importação do Stripe
print("\n2. Importando Stripe:")
try:
    import stripe
    stripe_key = os.getenv('STRIPE_SECRET_KEY')
    if stripe_key:
        stripe.api_key = stripe_key
        print(f"✅ Stripe configurado com chave: {stripe_key[:10]}...")
    else:
        print("❌ STRIPE_SECRET_KEY não encontrada!")
except Exception as e:
    print(f"❌ Erro ao importar Stripe: {e}")
    exit(1)

# 3. Testar importação do StripeService
print("\n3. Testando StripeService:")
try:
    from app.services.stripe_service import StripeService
    print("✅ StripeService importado com sucesso")
    
    # Testar o método create_checkout_session
    result = StripeService.create_checkout_session(
        plan_name="Teste - Grupo VIP",
        amount=29.90,
        success_url="https://t.me/bot?start=success_123",
        cancel_url="https://t.me/bot?start=cancel",
        metadata={'test': 'true'}
    )
    
    if result['success']:
        print("✅ Checkout session criada com sucesso!")
        print(f"   ID: {result['session_id']}")
        print(f"   URL: {result['url'][:60]}...")
    else:
        print(f"❌ Erro ao criar session: {result['error']}")
        
except Exception as e:
    print(f"❌ Erro ao importar/usar StripeService: {e}")
    import traceback
    traceback.print_exc()

# 4. Testar criação direta (como fallback)
print("\n4. Testando criação direta de checkout session:")
try:
    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{
            'price_data': {
                'currency': 'brl',
                'product_data': {
                    'name': 'Teste Direto',
                },
                'unit_amount': 2990,
            },
            'quantity': 1,
        }],
        mode='payment',
        success_url='https://example.com/success',
        cancel_url='https://example.com/cancel',
    )
    print("✅ Criação direta funcionou!")
    print(f"   URL: {session.url[:60]}...")
except Exception as e:
    print(f"❌ Erro na criação direta: {e}")

# 5. Verificar estrutura de pastas
print("\n5. Verificando estrutura de pastas:")
print(f"   Diretório atual: {os.getcwd()}")
print(f"   app/ existe: {os.path.exists('app')}")
print(f"   app/services/ existe: {os.path.exists('app/services')}")
print(f"   app/services/stripe_service.py existe: {os.path.exists('app/services/stripe_service.py')}")

print("\n=== FIM DO TESTE ===")

# Sugestões
print("\nSe algum teste falhou:")
print("1. Verifique se está executando da pasta raiz do projeto")
print("2. Confirme que app/services/stripe_service.py existe")
print("3. Verifique se o arquivo stripe_service.py foi salvo corretamente")
print("4. Reinicie o bot após fazer as correções")