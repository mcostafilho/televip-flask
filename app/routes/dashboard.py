# app/routes/dashboard.py
from flask import Blueprint, render_template, jsonify, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models import Group, Transaction, Subscription, Creator
from app.services.payment_service import PaymentService
from sqlalchemy import func, and_, desc
from datetime import datetime, timedelta

bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')

@bp.route('/')
@login_required
def index():
    """Dashboard principal com estatísticas de ganhos"""
    # Parâmetro opcional para filtrar por grupo
    group_id = request.args.get('group_id', type=int)
    selected_group = None
    
    # Buscar grupos do criador
    groups = Group.query.filter_by(creator_id=current_user.id).all()
    
    # Se um grupo específico foi selecionado
    if group_id:
        selected_group = Group.query.filter_by(id=group_id, creator_id=current_user.id).first()
        if selected_group:
            groups = [selected_group]
    
    # Calcular estatísticas
    total_revenue = 0
    total_subscribers = 0
    total_transactions = 0
    
    for group in groups:
        # Receita do grupo
        group_revenue = db.session.query(func.sum(Transaction.amount)).join(
            Subscription
        ).filter(
            Subscription.group_id == group.id,
            Transaction.status == 'completed'
        ).scalar() or 0
        
        # Número de transações do grupo
        group_transactions = db.session.query(func.count(Transaction.id)).join(
            Subscription
        ).filter(
            Subscription.group_id == group.id,
            Transaction.status == 'completed'
        ).scalar() or 0
        
        # Adicionar aos totais
        total_revenue += group_revenue
        total_transactions += group_transactions
        
        # Adicionar informações ao objeto grupo
        group.total_revenue = group_revenue
        group.total_transactions = group_transactions
        
        # Contar assinantes ativos
        active_subs = Subscription.query.filter_by(
            group_id=group.id,
            status='active'
        ).count()
        total_subscribers += active_subs
    
    # Transações recentes
    recent_transactions_query = Transaction.query.join(
        Subscription
    ).join(
        Group
    ).filter(
        Group.creator_id == current_user.id
    )
    
    if selected_group:
        recent_transactions_query = recent_transactions_query.filter(
            Subscription.group_id == selected_group.id
        )
    
    recent_transactions = recent_transactions_query.order_by(
        Transaction.created_at.desc()
    ).limit(10).all()
    
    # Assinantes (se um grupo específico estiver selecionado)
    subscribers = []
    if selected_group:
        subscribers = Subscription.query.filter_by(
            group_id=selected_group.id,
            status='active'
        ).order_by(Subscription.created_at.desc()).limit(5).all()
    
    # Dados para o gráfico (últimos 30 dias)
    revenue_chart_data = {
        'labels': [],
        'data': []
    }
    
    # Resetar para todos os grupos se estava filtrado
    all_groups = Group.query.filter_by(creator_id=current_user.id).all()
    
    # Passar variáveis individuais para o template
    return render_template('dashboard/index.html',
        # Variáveis principais
        balance=current_user.balance or 0,
        total_revenue=total_revenue,
        total_subscribers=total_subscribers,
        total_groups=len(all_groups),
        total_transactions=total_transactions,
        
        # Listas
        groups=all_groups,  # Sempre mostrar todos os grupos
        recent_transactions=recent_transactions,
        subscribers=subscribers,
        
        # Grupo selecionado (se houver)
        selected_group=selected_group,
        
        # Dados do gráfico
        revenue_chart_data=revenue_chart_data
    )

@bp.route('/profile')
@login_required
def profile():
    """Página de perfil do usuário"""
    # Verificar se o modelo Withdrawal existe
    try:
        from app.models import Withdrawal as RealWithdrawal
        Withdrawal = RealWithdrawal
        has_withdrawal_model = True
    except ImportError:
        has_withdrawal_model = False
    
    # Estatísticas do usuário
    total_withdrawn = 0
    if has_withdrawal_model:
        total_withdrawn = db.session.query(func.sum(Withdrawal.amount)).filter_by(
            creator_id=current_user.id,
            status='completed'
        ).scalar() or 0
    
    user_stats = {
        'total_earned': getattr(current_user, 'total_earned', 0) or 0,
        'balance': getattr(current_user, 'balance', 0) or 0,
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
    if has_withdrawal_model:
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
    telegram_username = request.form.get('telegram_username', '').strip()
    pix_key = request.form.get('pix_key', '').strip()
    
    # Validações
    if not name or len(name) < 3:
        flash('Nome deve ter pelo menos 3 caracteres', 'error')
        return redirect(url_for('dashboard.profile'))
    
    # Verificar se email já existe (se mudou)
    if email != current_user.email:
        existing = Creator.query.filter_by(email=email).first()
        if existing:
            flash('Email já está em uso', 'error')
            return redirect(url_for('dashboard.profile'))
    
    # Atualizar dados
    current_user.name = name
    current_user.email = email
    current_user.telegram_username = telegram_username
    current_user.pix_key = pix_key
    
    db.session.commit()
    flash('Perfil atualizado com sucesso!', 'success')
    
    return redirect(url_for('dashboard.profile'))

@bp.route('/withdraw', methods=['POST'])
@login_required
def withdraw():
    """Solicitar saque"""
    amount = float(request.form.get('amount', 0))
    pix_key = request.form.get('pix_key', '').strip()
    
    # Validações
    if amount < 10:
        flash('Valor mínimo para saque é R$ 10,00', 'error')
        return redirect(url_for('dashboard.index'))
    
    if amount > current_user.balance:
        flash('Saldo insuficiente', 'error')
        return redirect(url_for('dashboard.index'))
    
    if not pix_key:
        flash('Informe a chave PIX', 'error')
        return redirect(url_for('dashboard.index'))
    
    # Criar solicitação de saque
    withdrawal = Withdrawal(
        creator_id=current_user.id,
        amount=amount,
        pix_key=pix_key,
        status='pending'
    )
    
    # Atualizar saldo
    current_user.balance -= amount
    
    db.session.add(withdrawal)
    db.session.commit()
    
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
    """Página de analytics"""
    return render_template('dashboard/analytics.html')

# Adicionar imports necessários
try:
    from app.models import Withdrawal
except ImportError:
    # Se não tiver o modelo Withdrawal ainda
    class Withdrawal:
        pass