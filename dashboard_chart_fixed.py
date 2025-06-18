    # Dados para gráfico (últimos 7 dias) - VERSÃO CORRIGIDA
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=6)
    
    # Query simplificada e corrigida
    daily_revenue_query = text("""
        SELECT DATE(t.created_at) as date, 
               COALESCE(SUM(t.amount), 0) as total
        FROM transactions t
        JOIN subscriptions s ON t.subscription_id = s.id
        JOIN groups g ON s.group_id = g.id
        WHERE g.creator_id = :creator_id
          AND t.status = 'completed'
          AND DATE(t.created_at) >= :start_date
          AND DATE(t.created_at) <= :end_date
        GROUP BY DATE(t.created_at)
    """)
    
    daily_revenue_result = db.session.execute(daily_revenue_query, {
        'creator_id': current_user.id,
        'start_date': start_date.date(),
        'end_date': end_date.date()
    })
    
    # Converter para dicionário
    revenue_by_date = {}
    for row in daily_revenue_result:
        revenue_by_date[row.date] = float(row.total)
    
    # Preparar dados do gráfico com todos os dias
    chart_labels = []
    chart_data = []
    
    current_date = start_date.date()
    while current_date <= end_date.date():
        # Label no formato dd/mm
        chart_labels.append(current_date.strftime('%d/%m'))
        
        # Valor do dia ou 0
        value = revenue_by_date.get(current_date, 0.0)
        chart_data.append(value)
        
        current_date += timedelta(days=1)