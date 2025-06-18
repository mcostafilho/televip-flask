# Alternativa para a query de receita por plano (SQL direto)
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
        plan_data.append(float(row.total))