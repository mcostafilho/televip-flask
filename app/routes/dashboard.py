# app/routes/dashboard.py
from flask import Blueprint, render_template, jsonify, request, redirect, url_for, flash, session
from flask_login import login_required, current_user
from app import db
from app.models import Group, Transaction, Subscription, Creator, PricingPlan
from app.services.payment_service import PaymentService
from sqlalchemy import func, and_, desc
from datetime import datetime, timedelta

bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')

@bp.route('/')
@login_required
def index():
    """Dashboard principal com estatísticas"""
    # Buscar grupos do criador
    groups = Group.query.filter_by(creator_id=current_user.id).all()
    
    # Calcular estatísticas
    total_revenue = 0
    total_subscribers = 0
    active_groups = 0
    
    for group in groups:
        # Receita do grupo
        group_revenue = db.session.query(func.sum(Transaction.amount)).join(
            Subscription
        ).filter(
            Subscription.group_id == group.id,
            Transaction.status == 'completed'
        ).scalar() or 0
        
        group.total_revenue = group_revenue
        total_revenue += group_revenue
        
        # Assinantes ativos
        active_subs = Subscription.query.filter_by(
            group_id=group.id,
            status='active'
        ).count()
        
        group.total_subscribers = active_subs
        total_subscribers += active_subs
        
        # Grupos ativos
        if group.is_active:
            active_groups += 1
    
    # Dados para o gráfico (últimos 30 dias)
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=30)
    
    # Query para dados do gráfico
    chart_data_query = db.session.query(
        func.date(Transaction.created_at).label('date'),
        func.sum(Transaction.amount).label('total')
    ).join(
        Subscription
    ).join(
        Group
    ).filter(
        Group.creator_id == current_user.id,
        Transaction.status == 'completed',
        Transaction.created_at >= start_date,
        Transaction.created_at <= end_date
    ).group_by(
        func.date(Transaction.created_at)
    ).order_by('date')
    
    # Preparar dados do gráfico
    chart_labels = []
    chart_data = []
    date_revenue = {row.date: float(row.total) for row in chart_data_query}
    
    current_date = start_date.date()
    while current_date <= end_date.date():
        chart_labels.append(current_date.strftime('%d/%m'))
        chart_data.append(date_revenue.get(current_date, 0))
        current_date += timedelta(days=1)
    
    # Usar o saldo do próprio usuário
    balance = current_user.balance or 0
    
    # Transações recentes
    recent_transactions = Transaction.query.join(
        Subscription
    ).join(
        Group
    ).filter(
        Group.creator_id == current_user.id
    ).order_by(
        Transaction.created_at.desc()
    ).limit(5).all()
    
    return render_template('dashboard/index.html',
        # Estatísticas
        balance=balance,
        total_revenue=total_revenue,
        total_subscribers=total_subscribers,
        total_groups=len(groups),
        active_groups=active_groups,
        
        # Grupos
        groups=groups,
        
        # Transações
        recent_transactions=recent_transactions,
        
        # Dados do gráfico
        chart_labels=chart_labels,
        chart_data=chart_data
    )

@bp.route('/profile')
@login_required
def profile():
    """Página de perfil do usuário"""
    # Verificar se o modelo Withdrawal existe
    try:
        from app.models import Withdrawal
        has_withdrawal_model = True
    except ImportError:
        has_withdrawal_model = False
        Withdrawal = None
    
    # Estatísticas do usuário
    total_withdrawn = 0
    if has_withdrawal_model and Withdrawal:
        total_withdrawn = db.session.query(func.sum(Withdrawal.amount)).filter_by(
            creator_id=current_user.id,
            status='completed'
        ).scalar() or 0
    
    # Total ganho (receita total)
    total_earned = db.session.query(func.sum(Transaction.amount)).join(
        Subscription
    ).join(
        Group
    ).filter(
        Group.creator_id == current_user.id,
        Transaction.status == 'completed'
    ).scalar() or 0
    
    user_stats = {
        'total_earned': total_earned,
        'balance': current_user.balance or 0,
        'total_withdrawn': total_withdrawn,
        'total_groups': Group.query.filter_by(creator_id=current_user.id).count(),
        'total_subscribers': db.session.query(func.count(Subscription.id)).join(
            Group
        ).filter(
            Group.creator_id == current_user.id,
            Subscription.status == 'active'
        ).scalar() or 0,
        'member_since': current_user.created_at.strftime('%d/%m/%Y') if hasattr(current_user, 'created_at') and current_user.created_at else 'N/A'
    }
    
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
    
    # Saques recentes
    recent_withdrawals = []
    if has_withdrawal_model and Withdrawal:
        recent_withdrawals = Withdrawal.query.filter_by(
            creator_id=current_user.id
        ).order_by(
            Withdrawal.created_at.desc()
        ).limit(5).all()
    
    return render_template(
        'dashboard/profile.html', 
        user=current_user,
        stats=user_stats,
        recent_transactions=recent_transactions,
        recent_withdrawals=recent_withdrawals
    )

@bp.route('/profile/update', methods=['POST'])
@login_required
def update_profile():
    """Atualizar informações do perfil"""
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip()
    
    if not name or not email:
        flash('Nome e email são obrigatórios.', 'error')
        return redirect(url_for('dashboard.profile'))
    
    # Verificar se email já existe
    if email != current_user.email:
        existing = Creator.query.filter_by(email=email).first()
        if existing:
            flash('Este email já está em uso.', 'error')
            return redirect(url_for('dashboard.profile'))
    
    # Atualizar dados
    current_user.name = name
    current_user.email = email
    
    try:
        db.session.commit()
        flash('Perfil atualizado com sucesso!', 'success')
    except:
        db.session.rollback()
        flash('Erro ao atualizar perfil.', 'error')
    
    return redirect(url_for('dashboard.profile'))

@bp.route('/withdraw', methods=['POST'])
@login_required
def withdraw():
    """Solicitar saque"""
    amount = float(request.form.get('amount', 0))
    
    if amount <= 0:
        flash('Valor inválido.', 'error')
        return redirect(url_for('dashboard.index'))
    
    if amount > current_user.balance:
        flash('Saldo insuficiente.', 'error')
        return redirect(url_for('dashboard.index'))
    
    # TODO: Criar registro de saque
    flash(f'Saque de R$ {amount:.2f} solicitado com sucesso! Processamento em até 24h.', 'success')
    return redirect(url_for('dashboard.index'))

@bp.route('/transactions')
@login_required
def transactions():
    """Página de listagem de todas as transações"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # Query de transações
    transactions_query = Transaction.query.join(
        Subscription
    ).join(
        Group
    ).filter(
        Group.creator_id == current_user.id
    ).order_by(
        Transaction.created_at.desc()
    )
    
    # Paginação
    pagination = transactions_query.paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )
    
    return render_template(
        'dashboard/transactions.html',
        transactions=pagination.items,
        pagination=pagination,
        PaymentService=PaymentService
    )

@bp.route('/analytics')
@login_required
def analytics():
    """Página de analytics com estatísticas detalhadas"""
    # Obter período selecionado (padrão: 30 dias)
    period = request.args.get('period', '30')
    
    # Converter período para dias
    days = int(period)
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    # Buscar grupos do criador
    groups = Group.query.filter_by(creator_id=current_user.id).all()
    
    # Estatísticas gerais
    # Receita total no período
    total_revenue = db.session.query(func.sum(Transaction.amount)).join(
        Subscription
    ).join(
        Group
    ).filter(
        Group.creator_id == current_user.id,
        Transaction.status == 'completed',
        Transaction.created_at >= start_date,
        Transaction.created_at <= end_date
    ).scalar() or 0
    
    # Total de transações no período
    total_transactions = Transaction.query.join(
        Subscription
    ).join(
        Group
    ).filter(
        Group.creator_id == current_user.id,
        Transaction.status == 'completed',
        Transaction.created_at >= start_date,
        Transaction.created_at <= end_date
    ).count()
    
    # Ticket médio
    average_ticket = total_revenue / total_transactions if total_transactions > 0 else 0
    
    # Total de assinantes ativos
    total_subscribers = db.session.query(func.count(Subscription.id)).join(
        Group
    ).filter(
        Group.creator_id == current_user.id,
        Subscription.status == 'active'
    ).scalar() or 0
    
    # Novos assinantes no período
    new_subscribers = db.session.query(func.count(Subscription.id)).join(
        Group
    ).filter(
        Group.creator_id == current_user.id,
        Subscription.created_at >= start_date,
        Subscription.created_at <= end_date
    ).scalar() or 0
    
    # Preparar dados para gráficos
    
    # 1. Receita por dia
    revenue_by_day_query = db.session.query(
        func.date(Transaction.created_at).label('date'),
        func.sum(Transaction.amount).label('total')
    ).join(
        Subscription
    ).join(
        Group
    ).filter(
        Group.creator_id == current_user.id,
        Transaction.status == 'completed',
        Transaction.created_at >= start_date,
        Transaction.created_at <= end_date
    ).group_by(
        func.date(Transaction.created_at)
    ).order_by('date')
    
    # Preparar arrays para o gráfico
    revenue_labels = []
    revenue_data = []
    date_revenue = {row.date: float(row.total) for row in revenue_by_day_query}
    
    current_date = start_date.date()
    while current_date <= end_date.date():
        revenue_labels.append(current_date.strftime('%d/%m'))
        revenue_data.append(date_revenue.get(current_date, 0))
        current_date += timedelta(days=1)
    
    # 2. Novos assinantes por dia
    subscribers_by_day_query = db.session.query(
        func.date(Subscription.created_at).label('date'),
        func.count(Subscription.id).label('count')
    ).join(
        Group
    ).filter(
        Group.creator_id == current_user.id,
        Subscription.created_at >= start_date,
        Subscription.created_at <= end_date
    ).group_by(
        func.date(Subscription.created_at)
    ).order_by('date')
    
    # Preparar arrays para o gráfico
    subscribers_labels = []
    subscribers_data = []
    date_subscribers = {row.date: row.count for row in subscribers_by_day_query}
    
    current_date = start_date.date()
    while current_date <= end_date.date():
        subscribers_labels.append(current_date.strftime('%d/%m'))
        subscribers_data.append(date_subscribers.get(current_date, 0))
        current_date += timedelta(days=1)
    
    # 3. Receita por grupo (top 5)
    revenue_by_group_query = db.session.query(
        Group.name,
        func.sum(Transaction.amount).label('total')
    ).join(
        Subscription, Subscription.group_id == Group.id
    ).join(
        Transaction, Transaction.subscription_id == Subscription.id
    ).filter(
        Group.creator_id == current_user.id,
        Transaction.status == 'completed',
        Transaction.created_at >= start_date,
        Transaction.created_at <= end_date
    ).group_by(
        Group.id, Group.name
    ).order_by(
        desc('total')
    ).limit(5)
    
    group_labels = []
    group_data = []
    for row in revenue_by_group_query:
        group_labels.append(row.name)
        group_data.append(float(row.total))
    
    # 4. Receita por plano
    revenue_by_plan_query = db.session.query(
        PricingPlan.name,
        func.sum(Transaction.amount).label('total')
    ).join(
        Subscription, Subscription.plan_id == PricingPlan.id
    ).join(
        Transaction, Transaction.subscription_id == Subscription.id
    ).join(
        Group, Group.id == Subscription.group_id
    ).filter(
        Group.creator_id == current_user.id,
        Transaction.status == 'completed',
        Transaction.created_at >= start_date,
        Transaction.created_at <= end_date
    ).group_by(
        PricingPlan.id, PricingPlan.name
    ).order_by(
        desc('total')
    )
    
    plan_labels = []
    plan_data = []
    for row in revenue_by_plan_query:
        plan_labels.append(row.name)
        plan_data.append(float(row.total))
    
    # Atualizar estatísticas dos grupos para a tabela
    for group in groups:
        # Receita do grupo no período
        group.period_revenue = db.session.query(func.sum(Transaction.amount)).join(
            Subscription
        ).filter(
            Subscription.group_id == group.id,
            Transaction.status == 'completed',
            Transaction.created_at >= start_date,
            Transaction.created_at <= end_date
        ).scalar() or 0
        
        # Total de assinantes ativos
        group.total_subscribers = Subscription.query.filter_by(
            group_id=group.id,
            status='active'
        ).count()
        
        # Ticket médio do grupo
        group_transactions = Transaction.query.join(
            Subscription
        ).filter(
            Subscription.group_id == group.id,
            Transaction.status == 'completed',
            Transaction.created_at >= start_date,
            Transaction.created_at <= end_date
        ).count()
        
        group.average_ticket = group.period_revenue / group_transactions if group_transactions > 0 else 0
    
    # Preparar objeto de estatísticas
    stats = {
        'total_revenue': total_revenue,
        'total_transactions': total_transactions,
        'average_ticket': average_ticket,
        'total_subscribers': total_subscribers,
        'new_subscribers': new_subscribers
    }
    
    # Preparar dados dos gráficos
    charts_data = {
        'revenue_by_day': {
            'labels': revenue_labels,
            'data': revenue_data
        },
        'subscribers_by_day': {
            'labels': subscribers_labels,
            'data': subscribers_data
        },
        'revenue_by_group': {
            'labels': group_labels,
            'data': group_data
        },
        'revenue_by_plan': {
            'labels': plan_labels,
            'data': plan_data
        }
    }
    
    return render_template(
        'dashboard/analytics.html',
        stats=stats,
        period=period,
        groups=groups,
        charts_data=charts_data
    )

# Adicionar imports necessários
try:
    from app.models import Withdrawal
except ImportError:
    # Se não tiver o modelo Withdrawal ainda
    class Withdrawal:
        pass