"""
Script para verificar quais campos existem no modelo Transaction
Salve como: check_transaction_fields.py
Execute: python check_transaction_fields.py
"""
import os
import sys
from datetime import datetime

# Adicionar o diretório ao path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import Transaction

def check_transaction_model():
    """Verificar campos do modelo Transaction"""
    app = create_app()
    
    with app.app_context():
        print("🔍 Verificando modelo Transaction...")
        print("=" * 60)
        
        # Listar todos os atributos da classe
        print("\n📋 Campos definidos no modelo Transaction:")
        
        # Pegar colunas do SQLAlchemy
        for column in Transaction.__table__.columns:
            print(f"   - {column.name}: {column.type}")
        
        # Verificar campos específicos
        print("\n✅ Verificação de campos críticos:")
        critical_fields = [
            'id',
            'subscription_id',
            'amount',
            'fee',
            'fee_amount',
            'net_amount',
            'payment_method',
            'payment_id',
            'stripe_session_id',
            'stripe_payment_intent_id',
            'status',
            'created_at'
        ]
        
        for field in critical_fields:
            if hasattr(Transaction, field):
                print(f"   ✅ {field}: EXISTE")
            else:
                print(f"   ❌ {field}: NÃO EXISTE")
        
        # Criar transação de teste para ver campos aceitos
        print("\n🧪 Testando criação de Transaction...")
        try:
            # Não vamos salvar, apenas testar
            test_transaction = Transaction(
                subscription_id=1,
                amount=100.00,
                status='test'
            )
            print("   ✅ Criação básica funciona")
            
            # Verificar campos disponíveis
            print("\n📊 Campos disponíveis na instância:")
            for attr in dir(test_transaction):
                if not attr.startswith('_') and hasattr(test_transaction, attr):
                    value = getattr(test_transaction, attr, None)
                    if not callable(value):
                        print(f"   - {attr}")
                        
        except Exception as e:
            print(f"   ❌ Erro ao criar Transaction: {e}")

if __name__ == "__main__":
    check_transaction_model()