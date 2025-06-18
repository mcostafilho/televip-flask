#!/usr/bin/env python3
"""
Script para verificar se tudo está funcionando
Execute: python test_payment_flow.py
"""
import os
from dotenv import load_dotenv

load_dotenv()

print("🧪 VERIFICANDO SISTEMA DE PAGAMENTOS")
print("=" * 40)

# 1. Verificar variáveis de ambiente
print("1️⃣ Variáveis de ambiente:")
stripe_key = os.getenv('STRIPE_SECRET_KEY')
bot_token = os.getenv('BOT_TOKEN') or os.getenv('TELEGRAM_BOT_TOKEN')
bot_username = os.getenv('TELEGRAM_BOT_USERNAME') or os.getenv('BOT_USERNAME')

print(f"   Stripe: {'✅ Configurado' if stripe_key else '❌ Faltando'}")
print(f"   Bot Token: {'✅ Configurado' if bot_token else '❌ Faltando'}")
print(f"   Bot Username: {'✅ ' + bot_username if bot_username else '⚠️  Não configurado (opcional)'}")

# 2. Verificar banco de dados
print("\n2️⃣ Banco de dados:")
try:
    from app import create_app, db
    from app.models import Group, PricingPlan
    
    app = create_app()
    with app.app_context():
        groups = Group.query.filter_by(is_active=True).count()
        plans = PricingPlan.query.filter_by(is_active=True).count()
        
        print(f"   Grupos ativos: {groups}")
        print(f"   Planos ativos: {plans}")
        
        if groups == 0:
            print("   ⚠️  Crie grupos no dashboard web!")
except Exception as e:
    print(f"   ❌ Erro: {e}")

# 3. Testar Stripe
print("\n3️⃣ Conexão com Stripe:")
try:
    import stripe
    stripe.api_key = stripe_key
    
    # Teste simples
    stripe.Product.list(limit=1)
    print("   ✅ Conexão OK")
    print(f"   📍 Modo: {'TESTE' if stripe_key.startswith('sk_test_') else 'PRODUÇÃO'}")
except Exception as e:
    print(f"   ❌ Erro: {e}")

print("\n" + "=" * 40)
print("🚀 FLUXO DE TESTE:")
print("1. No Telegram, envie: /start g_3")
print("2. Escolha um plano")
print("3. Selecione 'Cartão (Stripe)'")
print("4. Complete o pagamento")
print("5. Você receberá o link do grupo!")

if not bot_username:
    print("\n⚠️  Configure BOT_USERNAME no .env para links melhores")
