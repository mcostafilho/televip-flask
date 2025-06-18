#!/usr/bin/env python3
"""Testar se o analytics está funcionando"""
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app

app = create_app()

with app.app_context():
    with app.test_client() as client:
        # Simular login (ajuste conforme necessário)
        # client.post('/login', data={'email': 'admin@example.com', 'password': 'senha'})
        
        # Tentar acessar analytics
        response = client.get('/dashboard/analytics')
        
        if response.status_code == 200:
            print("✅ Analytics funcionando!")
        else:
            print(f"❌ Erro no analytics: {response.status_code}")
            if response.data:
                print("Detalhes:", response.data.decode('utf-8')[:500])
