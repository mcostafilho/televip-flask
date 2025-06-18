#!/usr/bin/env python3
"""Script para testar se os imports estão corretos"""
try:
    print("Testando imports do bot...")
    from bot.handlers.payment import (
        start_payment, handle_payment_method, 
        list_user_subscriptions, handle_payment_success,
        check_payment_status, handle_payment_error
    )
    print("✅ Todos os imports OK!")
except ImportError as e:
    print(f"❌ Erro de import: {e}")
    
try:
    from bot.main import main
    print("✅ Main importado com sucesso!")
except ImportError as e:
    print(f"❌ Erro ao importar main: {e}")
