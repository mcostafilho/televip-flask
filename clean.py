#!/usr/bin/env python3
"""
Script corrigido para limpar TODAS as assinaturas
Execute: python clean_fixed.py
"""
import os
import sys
from pathlib import Path

# Adicionar o diretório ao path
sys.path.insert(0, str(Path(__file__).parent))

# Configurar ambiente Flask
os.environ['FLASK_APP'] = 'run.py'

from app import create_app, db
from app.models import Subscription, Transaction, Creator

def clean_all():
    """Limpar tudo rapidamente"""
    app = create_app()
    
    with app.app_context():
        print("🧹 LIMPANDO BANCO DE DADOS...")
        
        try:
            # Estatísticas antes
            subs = Subscription.query.count()
            trans = Transaction.query.count()
            
            print(f"\n📊 Antes da limpeza:")
            print(f"  - Assinaturas: {subs}")
            print(f"  - Transações: {trans}")
            
            # Deletar transações primeiro (foreign key)
            deleted_trans = Transaction.query.delete()
            print(f"\n🗑️ Deletando {deleted_trans} transações...")
            
            # Deletar assinaturas
            deleted_subs = Subscription.query.delete()
            print(f"🗑️ Deletando {deleted_subs} assinaturas...")
            
            # Resetar saldos dos criadores individualmente
            creators = Creator.query.all()
            for creator in creators:
                # Verificar se os atributos existem
                if hasattr(creator, 'available_balance'):
                    creator.available_balance = 0
                if hasattr(creator, 'pending_balance'):
                    creator.pending_balance = 0
                if hasattr(creator, 'total_earned'):
                    creator.total_earned = 0
            
            print(f"🔄 Resetando saldos de {len(creators)} criadores...")
            
            # Salvar tudo
            db.session.commit()
            
            # Verificar resultado
            subs_after = Subscription.query.count()
            trans_after = Transaction.query.count()
            
            print(f"\n✅ LIMPEZA CONCLUÍDA!")
            print(f"\n📊 Após a limpeza:")
            print(f"  - Assinaturas: {subs_after}")
            print(f"  - Transações: {trans_after}")
            print(f"  - Saldos dos criadores: Zerados")
            
        except Exception as e:
            db.session.rollback()
            print(f"\n❌ ERRO: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    print("=" * 50)
    print("⚠️  LIMPEZA TOTAL DO BANCO")
    print("=" * 50)
    print("\nIsso irá DELETAR:")
    print("- TODAS as assinaturas")
    print("- TODAS as transações") 
    print("- ZERAR saldos dos criadores")
    
    confirm = input("\nTem certeza? (digite SIM): ")
    
    if confirm.upper() == "SIM":
        clean_all()
    else:
        print("\n❌ Cancelado")