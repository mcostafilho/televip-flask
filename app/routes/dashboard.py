# app/routes/dashboard.py
from flask import Blueprint, render_template, jsonify, request, redirect, url_for, flash, session
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
    
    # Atualizar dados básicos
    current_user.name = name
    current_user.email = email
    
    # Atualizar campos opcionais se existirem no modelo
    if hasattr(current_user, 'telegram_username'):
        current_user.telegram_username = telegram_username
    if hasattr(current_user, 'pix_key'):
        current_user.pix_key = pix_key
    
    # Verificar se precisa alterar senha
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    
    if current_password and new_password:
        # Verificar senha atual
        if not current_user.check_password(current_password):
            flash('Senha atual incorreta', 'error')
            return redirect(url_for('dashboard.profile'))
        
        # Verificar se as novas senhas coincidem
        if new_password != confirm_password:
            flash('As novas senhas não coincidem', 'error')
            return redirect(url_for('dashboard.profile'))
        
        # Verificar tamanho mínimo
        if len(new_password) < 6:
            flash('A nova senha deve ter pelo menos 6 caracteres', 'error')
            return redirect(url_for('dashboard.profile'))
        
        # Atualizar senha
        current_user.set_password(new_password)
        flash('Senha alterada com sucesso!', 'success')
    
    # Salvar alterações
    db.session.commit()
    flash('Perfil atualizado com sucesso!', 'success')
    
    return redirect(url_for('dashboard.profile'))

@bp.route('/withdraw', methods=['POST'])
@login_required
def withdraw():
    """Solicitar saque"""
    amount = float(request.form.get('amount', 0))
    pix_key = request.form.get('pix_key')
    
    # Validações
    if amount < 10:
        flash('O valor mínimo para saque é R$ 10,00', 'error')
        return redirect(url_for('dashboard.index'))
    
    if amount > current_user.balance:
        flash('Saldo insuficiente para este saque.', 'error')
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
    """Página de analytics"""
    return render_template('dashboard/analytics.html')

# Adicionar imports necessários
try:
    from app.models import Withdrawal
except ImportError:
    # Se não tiver o modelo Withdrawal ainda
    class Withdrawal:
        pass