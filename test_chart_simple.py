#!/usr/bin/env python3
"""Teste simples do gráfico"""
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app

app = create_app()

with app.app_context():
    # Simular acesso ao dashboard
    with app.test_client() as client:
        # Fazer login (ajuste conforme necessário)
        response = client.get('/dashboard/')
        
        if response.status_code == 200:
            # Verificar se os dados estão no HTML
            html = response.data.decode('utf-8')
            
            # Procurar pelos dados do gráfico
            if 'chart_data' in html:
                print("✅ Variável chart_data encontrada no HTML")
                
                # Extrair os dados
                import re
                match = re.search(r'chart_data[\s]*:[\s]*\[([^\]]+)\]', html)
                if match:
                    data = match.group(1)
                    print(f"📊 Dados do gráfico: [{data}]")
                else:
                    print("❌ Não foi possível extrair os dados")
            else:
                print("❌ chart_data não encontrado no HTML")
        else:
            print(f"❌ Erro ao acessar dashboard: {response.status_code}")
