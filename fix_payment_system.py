#!/usr/bin/env python3
"""
Script para corrigir o erro de joins ambíguos no analytics
Execute: python fix_analytics_joins.py
"""
import os
import shutil
from datetime import datetime

def fix_analytics_route():
    """Corrigir joins ambíguos na rota analytics"""
    print("🔧 Corrigindo joins ambíguos no analytics...")
    print("=" * 50)
    
    dashboard_file = "app/routes/dashboard.py"
    
    if not os.path.exists(dashboard_file):
        print(f"❌ Arquivo {dashboard_file} não encontrado!")
        return False
    
    # Fazer backup
    backup_file = f"{dashboard_file}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"📋 Criando backup: {backup_file}")
    shutil.copy2(dashboard_file, backup_file)
    
    # Ler conteúdo
    with open(dashboard_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print("📝 Aplicando correções nos joins...")
    
    # Correção 1: Query de receita por plano (mais problemática)
    old_plan_revenue = '''plan_revenue = db.session.query(
        PricingPlan.name,
        func.sum(Transaction.amount).label('total')
    ).join(
        Subscription, PricingPlan.id == Subscription.plan_id
    ).join(
        Transaction
    ).join(
        Group
    ).filter('''
    
    new_plan_revenue = '''plan_revenue = db.session.query(
        PricingPlan.name,
        func.sum(Transaction.amount).label('total')
    ).select_from(
        PricingPlan
    ).join(
        Subscription, PricingPlan.id == Subscription.plan_id
    ).join(
        Transaction, Transaction.subscription_id == Subscription.id
    ).join(
        Group, Group.id == Subscription.group_id
    ).filter('''
    
    if old_plan_revenue in content:
        content = content.replace(old_plan_revenue, new_plan_revenue)
        print("✅ Corrigido: Query de receita por plano")
    
    # Correção 2: Query de receita por grupo
    old_group_revenue = '''group_revenue = db.session.query(
        Group.name,
        func.sum(Transaction.amount).label('total')
    ).join(
        Subscription, Group.id == Subscription.group_id
    ).join(
        Transaction
    ).filter('''
    
    new_group_revenue = '''group_revenue = db.session.query(
        Group.name,
        func.sum(Transaction.amount).label('total')
    ).select_from(
        Group
    ).join(
        Subscription, Group.id == Subscription.group_id
    ).join(
        Transaction, Transaction.subscription_id == Subscription.id
    ).filter('''
    
    if old_group_revenue in content:
        content = content.replace(old_group_revenue, new_group_revenue)
        print("✅ Corrigido: Query de receita por grupo")
    
    # Correção 3: Garantir que todas as queries tenham joins explícitos
    # Procurar por joins sem condição explícita
    content = content.replace(
        ').join(\n        Transaction\n    )',
        ').join(\n        Transaction, Transaction.subscription_id == Subscription.id\n    )'
    )
    
    # Salvar arquivo corrigido
    with open(dashboard_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ Dashboard.py corrigido!")
    return True

def create_analytics_fix_alternative():
    """Criar versão alternativa usando SQL direto"""
    print("\n📝 Criando versão alternativa com SQL direto...")
    
    alternative_code = '''# Alternativa para a query de receita por plano (SQL direto)
    plan_revenue_sql = text("""
        SELECT p.name, SUM(t.amount) as total
        FROM pricing_plans p
        JOIN subscriptions s ON p.id = s.plan_id
        JOIN transactions t ON t.subscription_id = s.id
        JOIN groups g ON g.id = s.group_id
        WHERE g.creator_id = :creator_id
          AND t.status = 'completed'
          AND t.created_at >= :start_date
        GROUP BY p.id, p.name
    """)
    
    plan_revenue_result = db.session.execute(plan_revenue_sql, {
        'creator_id': current_user.id,
        'start_date': start_date
    })
    
    plan_labels = []
    plan_data = []
    for row in plan_revenue_result:
        plan_labels.append(row.name)
        plan_data.append(float(row.total))'''
    
    with open('analytics_alternative.py', 'w', encoding='utf-8') as f:
        f.write(alternative_code)
    
    print("✅ Código alternativo salvo em: analytics_alternative.py")

def create_test_analytics():
    """Criar script de teste do analytics"""
    print("\n📝 Criando script de teste...")
    
    test_script = '''#!/usr/bin/env python3
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
'''
    
    with open('test_analytics.py', 'w', encoding='utf-8') as f:
        f.write(test_script)
    
    print("✅ Script de teste criado: test_analytics.py")

def show_join_explanation():
    """Mostrar explicação sobre o problema"""
    print("\n📚 EXPLICAÇÃO DO PROBLEMA:")
    print("=" * 50)
    print("""
O erro ocorre porque o SQLAlchemy não consegue determinar automaticamente
como fazer o JOIN entre as tabelas quando há múltiplas relações possíveis.

Por exemplo:
- Transaction tem subscription_id (FK para Subscription)
- Subscription tem group_id (FK para Group) e plan_id (FK para PricingPlan)
- Group tem creator_id (FK para Creator)

Quando você faz .join(Transaction).join(Group), o SQLAlchemy não sabe
se deve usar:
1. Transaction -> Subscription -> Group
2. Alguma outra rota de relacionamento

SOLUÇÃO:
Especificar explicitamente as condições de JOIN:
- .join(Transaction, Transaction.subscription_id == Subscription.id)
- .join(Group, Group.id == Subscription.group_id)

Ou usar select_from() para definir a tabela inicial:
- .select_from(PricingPlan).join(Subscription, ...).join(Transaction, ...)
""")

def main():
    """Função principal"""
    print("🚀 CORREÇÃO DE JOINS AMBÍGUOS NO ANALYTICS")
    print("=" * 50)
    
    # 1. Aplicar correção
    success = fix_analytics_route()
    
    if success:
        # 2. Criar arquivos auxiliares
        create_analytics_fix_alternative()
        create_test_analytics()
        
        # 3. Mostrar explicação
        show_join_explanation()
        
        print("\n✅ CORREÇÃO APLICADA!")
        print("\n📋 PRÓXIMOS PASSOS:")
        print("1. Reinicie o Flask")
        print("2. Acesse /dashboard/analytics")
        print("3. Deve funcionar sem erros")
        
        print("\n💡 Se ainda der erro:")
        print("- Use o código SQL direto de 'analytics_alternative.py'")
        print("- Execute 'test_analytics.py' para testar")
    else:
        print("\n❌ Correção falhou!")
        print("Aplique manualmente as correções")

if __name__ == "__main__":
    main()