#!/usr/bin/env python3
'''Script para testar o sistema de pagamentos'''
import os
from dotenv import load_dotenv

load_dotenv()

def test_stripe():
    try:
        import stripe
        stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
        
        # Teste simples
        stripe.Product.list(limit=1)
        print("✅ Conexão com Stripe OK!")
        
        # Mostrar modo
        if stripe.api_key.startswith('sk_test_'):
            print("📍 Modo: TESTE")
        else:
            print("📍 Modo: PRODUÇÃO")
            
        return True
    except Exception as e:
        print(f"❌ Erro Stripe: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Testando sistema de pagamentos...")
    print("=" * 40)
    test_stripe()
