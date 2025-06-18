@bp.route('/')
@login_required
def index():
    """Dashboard principal do criador"""
    # Calcular saldo com as taxas corretas
    balance_info = calculate_balance(current_user.id)
    
    # Estatísticas
    total_groups = Group.query.filter_by(creator_id=current_user.id).count()
    active_groups = Group.query.filter_by(creator_id=current_user.id, is_active=True).count()
    
    # Assinantes ativos
    active_subscriptions = Subscription.query.join(Group).filter(
        Group.creator_id == current_user.id,
        Subscription.status == 'active'
    ).count()
    
    # Grupos do criador (para a tabela)
    groups = Group.query.filter_by(creator_id=current_user.id).order_by(
        Group.created_at.desc()
    ).all()
    
    # Calcular receita total de cada grupo
    for group in groups:
        group.total_revenue = db.session.query(
            func.sum(Transaction.amount)
        ).join(
            Subscription
        ).filter(
            Subscription.group_id == group.id,
            Transaction.status == 'completed'
        ).scalar() or 0
    
    # Transações recentes
    recent_transactions = Transaction.query.join(
        Subscription
    ).join(
        Group
    ).filter(
        Group.creator_id == current_user.id,
        Transaction.status == 'completed'
    ).order_by(
        Transaction.created_at.desc()
    ).limit(10).all()
    
    # Dados para gráfico (últimos 7 dias)
    from datetime import datetime, timedelta
    from sqlalchemy import func
    
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=7)
    
    daily_revenue = db.session.query(
        func.date(Transaction.created_at).label('date'),
        func.sum(Transaction.amount).label('total')
    ).join(
        Subscription
    ).join(
        Group
    ).filter(
        Group.creator_id == current_user.id,
        Transaction.status == 'completed',
        Transaction.created_at >= start_date
    ).group_by(
        func.date(Transaction.created_at)
    ).all()
    
    # Preparar dados do gráfico
    chart_labels = []
    chart_data = []
    current_date = start_date.date()
    
    revenue_dict = {r.date: float(r.total) for r in daily_revenue}
    
    while current_date <= end_date.date():
        chart_labels.append(current_date.strftime('%d/%m'))
        chart_data.append(revenue_dict.get(current_date, 0))
        current_date += timedelta(days=1)
    
    return render_template('dashboard/index.html',
        # Saldo e taxas
        available_balance=balance_info['available_balance'],
        balance=balance_info['available_balance'],  # Compatibilidade
        total_fees=balance_info['total_fees'],
        transaction_count=balance_info['transaction_count'],
        
        # Estatísticas gerais
        total_groups=total_groups,
        active_groups=active_groups,
        total_revenue=balance_info['total_received'],
        total_subscribers=active_subscriptions,  # Compatibilidade com template
        groups=groups,
        recent_transactions=recent_transactions,
        
        # Dados do gráfico
        chart_labels=chart_labels,
        chart_data=chart_data
    )
