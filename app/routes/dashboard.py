from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db
from app.models import Group, Subscription, Transaction, Withdrawal
from sqlalchemy import func, extract
from datetime import datetime, timedelta
import json

bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')

@bp.route('/')
@login_required
def index():
    """Dashboard principal do criador"""
    # Verificar se há um grupo específico selecionado
    group_id = request.args.get('group_id', type=int)
    selected_group = None
    
    # Buscar grupos do criador
    groups = current_user.groups.all()
    total_groups = len(groups)
    
    # Se um grupo específico foi selecionado
    if group_id:
        selected_group = Group.query.filter_by(id=group_id, creator_id=current_user.id).first()
        if selected_group:
            # Calcular estatísticas apenas deste grupo
            total_subscribers = Subscription.query.filter_by(
                group_id=group_id,
                status='active'
            ).count()
            
            # Receita apenas deste grupo
            total_revenue = db.session.query(
                func.sum(Transaction.net_amount)
            ).join(Subscription).filter(
                Subscription.group_id == group_id,
                Transaction.status == 'completed'
            ).scalar() or 0
            
            # Transações apenas deste grupo
            recent_transactions = Transaction.query.join(Subscription).filter(
                Subscription.group_id == group_id
            ).order_by(Transaction.created_at.desc()).limit(5).all()
            
            # Buscar assinantes do grupo
            subscribers = Subscription.query.filter_by(
                group_id=group_id
            ).order_by(Subscription.created_at.desc()).limit(5).all()
            
        else:
            # Grupo inválido, redirecionar
            return redirect(url_for('dashboard.index'))
    else:
        # Dados consolidados de todos os grupos
        total_subscribers = 0
        for group in groups:
            active_subs = Subscription.query.filter_by(
                group_id=group.id,
                status='active'
            ).count()
            total_subscribers += active_subs
            group.total_subscribers = active_subs
        
        # Receita total de todos os grupos
        total_revenue = current_user.total_earned or 0
        
        # Transações de todos os grupos
        if groups:
            group_ids = [g.id for g in groups]
            recent_transactions = Transaction.query.join(Subscription).filter(
                Subscription.group_id.in_(group_ids)
            ).order_by(Transaction.created_at.desc()).limit(5).all()
        else:
            recent_transactions = []
        
        subscribers = None
    
    # Dados do gráfico (últimos 30 dias)
    revenue_chart_data = get_revenue_chart_data(selected_group.id if selected_group else None)
    
    return render_template('dashboard/index.html',
                         groups=groups,
                         total_groups=total_groups,
                         total_subscribers=total_subscribers,
                         total_revenue=total_revenue,
                         balance=current_user.balance or 0,
                         recent_transactions=recent_transactions,
                         selected_group=selected_group,
                         subscribers=subscribers,
                         revenue_chart_data=revenue_chart_data)

def get_revenue_chart_data(group_id=None):
    """Obter dados reais do gráfico de receita dos últimos 30 dias"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=29)
    
    # Criar lista com todos os dias
    date_list = []
    current_date = start_date
    while current_date <= end_date:
        date_list.append(current_date.strftime('%d/%m'))
        current_date += timedelta(days=1)
    
    # Inicializar dados com zeros
    revenue_by_day = {date: 0 for date in date_list}
    
    # Query para buscar transações
    query = db.session.query(
        func.date(Transaction.created_at).label('date'),
        func.sum(Transaction.net_amount).label('total')
    ).join(Subscription)
    
    # Filtrar por grupo se especificado
    if group_id:
        query = query.filter(Subscription.group_id == group_id)
    else:
        # Todos os grupos do criador
        group_ids = [g.id for g in current_user.groups.all()]
        if group_ids:
            query = query.filter(Subscription.group_id.in_(group_ids))
    
    # Filtrar por período e status
    query = query.filter(
        Transaction.status == 'completed',
        Transaction.created_at >= start_date,
        Transaction.created_at <= end_date
    ).group_by(func.date(Transaction.created_at))
    
    # Executar query
    results = query.all()
    
    # Preencher dados reais
    for date, total in results:
        date_str = date.strftime('%d/%m')
        if date_str in revenue_by_day:
            revenue_by_day[date_str] = float(total)
    
    return {
        'labels': list(revenue_by_day.keys()),
        'data': list(revenue_by_day.values())
    }

@bp.route('/withdraw', methods=['POST'])
@login_required
def withdraw():
    """Solicitar saque"""
    amount = float(request.form.get('amount', 0))
    pix_key = request.form.get('pix_key')
    
    if amount > current_user.balance:
        flash('Saldo insuficiente!', 'error')
    elif amount < 10:
        flash('Valor mínimo para saque: R$ 10,00', 'error')
    else:
        withdrawal = Withdrawal(
            creator_id=current_user.id,
            amount=amount,
            pix_key=pix_key
        )
        db.session.add(withdrawal)
        db.session.commit()
        
        flash('Saque solicitado! Processamento em até 24h.', 'success')
    
    return redirect(url_for('dashboard.index'))

@bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """Perfil do criador"""
    if request.method == 'POST':
        # Atualizar dados do perfil
        current_user.name = request.form.get('name')
        current_user.email = request.form.get('email')
        
        # Verificar se mudou a senha
        new_password = request.form.get('new_password')
        if new_password:
            current_password = request.form.get('current_password')
            if current_user.check_password(current_password):
                current_user.set_password(new_password)
                flash('Senha atualizada com sucesso!', 'success')
            else:
                flash('Senha atual incorreta!', 'error')
                return redirect(url_for('dashboard.profile'))
        
        # Atualizar Telegram ID se fornecido
        telegram_id = request.form.get('telegram_id')
        if telegram_id:
            current_user.telegram_id = telegram_id
        
        db.session.commit()
        flash('Perfil atualizado com sucesso!', 'success')
        return redirect(url_for('dashboard.profile'))
    
    # Calcular estatísticas do perfil
    stats = {
        'total_groups': current_user.groups.count(),
        'total_subscribers': 0,
        'total_revenue': current_user.total_earned or 0,
        'pending_withdrawals': Withdrawal.query.filter_by(
            creator_id=current_user.id,
            status='pending'
        ).count()
    }
    
    # Contar total de assinantes
    for group in current_user.groups:
        stats['total_subscribers'] += Subscription.query.filter_by(
            group_id=group.id,
            status='active'
        ).count()
    
    return render_template('dashboard/profile.html', stats=stats)

@bp.route('/analytics')
@login_required
def analytics():
    """Analytics e relatórios detalhados"""
    # Período selecionado (padrão: últimos 30 dias)
    period = request.args.get('period', '30')
    
    if period == '7':
        start_date = datetime.now() - timedelta(days=7)
    elif period == '30':
        start_date = datetime.now() - timedelta(days=30)
    elif period == '90':
        start_date = datetime.now() - timedelta(days=90)
    else:
        start_date = datetime.now() - timedelta(days=30)
    
    # Grupos do criador
    groups = current_user.groups.all()
    group_ids = [g.id for g in groups]
    
    # Estatísticas gerais
    stats = {
        'total_revenue': 0,
        'total_transactions': 0,
        'total_subscribers': 0,
        'new_subscribers': 0,
        'churn_rate': 0,
        'average_ticket': 0
    }
    
    if group_ids:
        # Receita total no período
        stats['total_revenue'] = db.session.query(
            func.sum(Transaction.net_amount)
        ).join(Subscription).filter(
            Subscription.group_id.in_(group_ids),
            Transaction.status == 'completed',
            Transaction.created_at >= start_date
        ).scalar() or 0
        
        # Total de transações
        stats['total_transactions'] = Transaction.query.join(
            Subscription
        ).filter(
            Subscription.group_id.in_(group_ids),
            Transaction.status == 'completed',
            Transaction.created_at >= start_date
        ).count()
        
        # Assinantes ativos
        stats['total_subscribers'] = Subscription.query.filter(
            Subscription.group_id.in_(group_ids),
            Subscription.status == 'active'
        ).count()
        
        # Novos assinantes no período
        stats['new_subscribers'] = Subscription.query.filter(
            Subscription.group_id.in_(group_ids),
            Subscription.created_at >= start_date
        ).count()
        
        # Ticket médio
        if stats['total_transactions'] > 0:
            stats['average_ticket'] = stats['total_revenue'] / stats['total_transactions']
    
    # Dados para gráficos
    charts_data = {
        'revenue_by_day': get_analytics_chart_data('revenue', group_ids, start_date),
        'subscribers_by_day': get_analytics_chart_data('subscribers', group_ids, start_date),
        'revenue_by_group': get_revenue_by_group(group_ids, start_date),
        'revenue_by_plan': get_revenue_by_plan(group_ids, start_date)
    }
    
    return render_template('dashboard/analytics.html',
                         stats=stats,
                         charts_data=charts_data,
                         period=period,
                         groups=groups)

def get_analytics_chart_data(chart_type, group_ids, start_date):
    """Obter dados para gráficos do analytics"""
    if not group_ids:
        return {'labels': [], 'data': []}
        
    end_date = datetime.now()
    days_diff = (end_date - start_date).days
    
    # Criar lista de datas
    date_list = []
    current_date = start_date
    while current_date <= end_date:
        if days_diff > 30:
            date_list.append(current_date.strftime('%d/%m'))
        else:
            date_list.append(current_date.strftime('%d'))
        current_date += timedelta(days=1)
    
    # Inicializar dados
    data_by_day = {date: 0 for date in date_list}
    
    if chart_type == 'revenue':
        # Receita por dia
        query = db.session.query(
            func.date(Transaction.created_at).label('date'),
            func.sum(Transaction.net_amount).label('total')
        ).select_from(Transaction).join(
            Subscription, Transaction.subscription_id == Subscription.id
        ).filter(
            Subscription.group_id.in_(group_ids),
            Transaction.status == 'completed',
            Transaction.created_at >= start_date
        ).group_by(func.date(Transaction.created_at))
        
        results = query.all()
        
        for date, total in results:
            if days_diff > 30:
                date_str = date.strftime('%d/%m')
            else:
                date_str = date.strftime('%d')
            if date_str in data_by_day:
                data_by_day[date_str] = float(total)
    
    elif chart_type == 'subscribers':
        # Novos assinantes por dia
        query = db.session.query(
            func.date(Subscription.created_at).label('date'),
            func.count(Subscription.id).label('total')
        ).filter(
            Subscription.group_id.in_(group_ids),
            Subscription.created_at >= start_date
        ).group_by(func.date(Subscription.created_at))
        
        results = query.all()
        
        for date, total in results:
            if days_diff > 30:
                date_str = date.strftime('%d/%m')
            else:
                date_str = date.strftime('%d')
            if date_str in data_by_day:
                data_by_day[date_str] = total
    
    return {
        'labels': list(data_by_day.keys()),
        'data': list(data_by_day.values())
    }

def get_revenue_by_group(group_ids, start_date):
    """Receita por grupo"""
    if not group_ids:
        return {'labels': [], 'data': []}
    
    query = db.session.query(
        Group.name,
        func.sum(Transaction.net_amount).label('total')
    ).select_from(Group).join(
        Subscription, Group.id == Subscription.group_id
    ).join(
        Transaction, Subscription.id == Transaction.subscription_id
    ).filter(
        Group.id.in_(group_ids),
        Transaction.status == 'completed',
        Transaction.created_at >= start_date
    ).group_by(Group.id, Group.name)
    
    results = query.all()
    
    return {
        'labels': [r[0] for r in results] if results else [],
        'data': [float(r[1]) for r in results] if results else []
    }

def get_revenue_by_plan(group_ids, start_date):
    """Receita por plano"""
    from app.models import PricingPlan
    
    if not group_ids:
        return {'labels': [], 'data': []}
    
    query = db.session.query(
        PricingPlan.name,
        func.sum(Transaction.net_amount).label('total')
    ).select_from(PricingPlan).join(
        Subscription, PricingPlan.id == Subscription.plan_id
    ).join(
        Transaction, Subscription.id == Transaction.subscription_id
    ).filter(
        Subscription.group_id.in_(group_ids),
        Transaction.status == 'completed',
        Transaction.created_at >= start_date
    ).group_by(PricingPlan.id, PricingPlan.name)
    
    results = query.all()
    
    return {
        'labels': [r[0] for r in results] if results else [],
        'data': [float(r[1]) for r in results] if results else []
    }