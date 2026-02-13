# app/routes/dashboard.py
import logging
from flask import Blueprint, render_template, jsonify, request, redirect, url_for, flash, session
from flask_login import login_required, current_user
from app import db, limiter, cache
from app.models import Group, Transaction, Subscription, Creator, PricingPlan
from app.services.payment_service import PaymentService
from app.utils.security import generate_reset_token
from app.utils.email import send_password_reset_email
from app.utils.admin_helpers import get_effective_creator, is_admin_viewing

logger = logging.getLogger(__name__)
from sqlalchemy import func, and_, or_, desc
from datetime import datetime, timedelta
from decimal import Decimal

bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')

@cache.memoize(timeout=60)
def calculate_balance(creator_id):
    """Calcular saldo disponível e bloqueado (7 dias de retenção)"""
    from app.models import Transaction, Subscription, Group
    from datetime import datetime, timedelta
    
    # Data limite para saldo disponível (7 dias atrás)
    available_date = datetime.utcnow() - timedelta(days=7)
    
    # Buscar todas as transações completas
    transactions = Transaction.query.join(
        Subscription
    ).join(
        Group
    ).filter(
        Group.creator_id == creator_id,
        Transaction.status == 'completed'
    ).all()
    
    # Separar transações disponíveis e bloqueadas
    available_transactions = []
    blocked_transactions = []
    
    total_received = 0
    total_fees = 0
    available_balance = 0
    blocked_balance = 0
    
    for transaction in transactions:
        # Valor bruto da transação
        amount = float(transaction.amount)
        
        # Calcular taxas
        fixed_fee = 0.99  # Taxa fixa
        percentage_fee = amount * 0.0999  # 9,99%
        total_fee = fixed_fee + percentage_fee
        net_amount = amount - total_fee
        
        total_received += amount
        total_fees += total_fee
        
        # Usar created_at se paid_at não existir
        payment_date = getattr(transaction, 'paid_at', None) or transaction.created_at
        
        # Verificar se está disponível (mais de 7 dias)
        if payment_date and payment_date <= available_date:
            available_balance += net_amount
            available_transactions.append({
                'transaction': transaction,
                'net_amount': net_amount,
                'status': 'available'
            })
        else:
            blocked_balance += net_amount
            # Calcular dias restantes
            if payment_date:
                days_passed = (datetime.utcnow() - payment_date).days
                days_remaining = max(0, 7 - days_passed)
            else:
                days_remaining = 7
                
            blocked_transactions.append({
                'transaction': transaction,
                'net_amount': net_amount,
                'days_remaining': days_remaining,
                'status': 'blocked'
            })
    
    # Organizar transações bloqueadas por dias restantes
    blocked_by_days = {}
    for bt in blocked_transactions:
        days = bt['days_remaining']
        if days not in blocked_by_days:
            blocked_by_days[days] = {
                'amount': 0,
                'count': 0,
                'transactions': []
            }
        blocked_by_days[days]['amount'] += bt['net_amount']
        blocked_by_days[days]['count'] += 1
        blocked_by_days[days]['transactions'].append(bt)
    
    return {
        'total_received': total_received,
        'total_fees': total_fees,
        'available_balance': available_balance,
        'blocked_balance': blocked_balance,
        'total_balance': available_balance + blocked_balance,
        'transaction_count': len(transactions),
        'available_transactions': available_transactions,
        'blocked_transactions': blocked_transactions,
        'blocked_by_days': blocked_by_days
    }

@bp.route('/')
@login_required
def index():
    """Dashboard principal do criador"""
    effective = get_effective_creator()

    # Calcular saldo com as taxas corretas
    balance_info = calculate_balance(effective.id)

    # Buscar grupos do criador
    groups = Group.query.filter_by(creator_id=effective.id).all()

    # Calcular estatísticas
    total_groups = len(groups)
    active_groups = 0
    total_subscribers = 0

    for group in groups:
        # Receita do grupo (valor bruto)
        group_revenue = db.session.query(func.sum(Transaction.amount)).join(
            Subscription
        ).filter(
            Subscription.group_id == group.id,
            Transaction.status == 'completed'
        ).scalar() or 0

        group.total_revenue = float(group_revenue)

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

    # Transações recentes
    recent_transactions = Transaction.query.join(
        Subscription
    ).join(
        Group
    ).filter(
        Group.creator_id == effective.id,
        Transaction.status == 'completed'
    ).order_by(
        Transaction.created_at.desc()
    ).limit(10).all()

    # Dados para gráfico (últimos 7 dias)
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=6)

    from sqlalchemy import text

    daily_revenue_query = text("""
        SELECT DATE(t.created_at) as date,
               CAST(SUM(t.amount) AS DECIMAL) as total
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
        'creator_id': effective.id,
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d')
    })

    # Converter resultado para dicionário
    revenue_by_date = {}
    for row in daily_revenue_result:
        date_str = row.date
        if hasattr(row.date, 'strftime'):
            date_str = row.date.strftime('%Y-%m-%d')
        revenue_by_date[date_str] = float(row.total)

    # Preparar dados do gráfico
    chart_labels = []
    chart_data = []

    current_date = start_date
    while current_date <= end_date:
        label = current_date.strftime('%d/%m')
        chart_labels.append(label)

        date_key = current_date.strftime('%Y-%m-%d')
        value = revenue_by_date.get(date_key, 0.0)
        chart_data.append(float(value))

        current_date += timedelta(days=1)

    return render_template('dashboard/index.html',
        available_balance=balance_info['available_balance'],
        blocked_balance=balance_info['blocked_balance'],
        blocked_by_days=balance_info['blocked_by_days'],
        total_balance=balance_info['total_balance'],
        balance=balance_info['available_balance'],
        total_fees=balance_info['total_fees'],
        transaction_count=balance_info['transaction_count'],
        total_groups=total_groups,
        active_groups=active_groups,
        total_revenue=balance_info['total_received'],
        total_subscribers=total_subscribers,
        groups=groups,
        recent_transactions=recent_transactions,
        chart_labels=chart_labels,
        chart_data=chart_data
    )

@bp.route('/transactions')
@login_required
def transactions():
    """Listar todas as transações"""
    effective = get_effective_creator()
    page = request.args.get('page', 1, type=int)
    per_page = 20

    # Query base
    query = Transaction.query.join(
        Subscription
    ).join(
        Group
    ).filter(
        Group.creator_id == effective.id
    )

    # Filtros
    status = request.args.get('status')
    if status:
        query = query.filter(Transaction.status == status)

    group_id = request.args.get('group_id', type=int)
    if group_id:
        query = query.filter(Subscription.group_id == group_id)

    # Ordenar por data
    query = query.order_by(Transaction.created_at.desc())

    # Paginar
    transactions = query.paginate(page=page, per_page=per_page, error_out=False)

    # Buscar grupos para filtro
    groups = Group.query.filter_by(creator_id=effective.id).all()

    return render_template('dashboard/transactions.html',
        transactions=transactions,
        groups=groups
    )

@bp.route('/withdrawals')
@login_required
def withdrawals():
    """Histórico de saques"""
    # Implementar quando tiver o modelo de saques
    return render_template('dashboard/withdrawals.html')

@bp.route('/withdraw', methods=['POST'])
@login_required
@limiter.limit("5 per hour")
def withdraw():
    """Solicitar saque com validação de saldo"""
    if is_admin_viewing():
        flash('Acao nao permitida no modo admin.', 'warning')
        return redirect(url_for('dashboard.index'))

    from app.models import Withdrawal

    amount = request.form.get('amount', type=float)
    pix_key = current_user.pix_key

    if not pix_key:
        flash('Configure sua chave PIX no perfil antes de solicitar saque.', 'error')
        return redirect(url_for('dashboard.index'))

    # Minimum withdrawal: R$10.00
    if not amount or amount < 10:
        flash('Valor mínimo para saque é R$ 10,00', 'error')
        return redirect(url_for('dashboard.index'))

    # Calculate real available balance
    balance_info = calculate_balance(current_user.id)
    available_balance = balance_info['available_balance']

    # Subtract already-completed withdrawals
    total_withdrawn = db.session.query(
        func.coalesce(func.sum(Withdrawal.amount), Decimal('0'))
    ).filter(
        Withdrawal.creator_id == current_user.id,
        Withdrawal.status == 'completed'
    ).scalar()

    # Subtract pending withdrawals (already requested but not yet processed)
    pending_withdrawals = db.session.query(
        func.coalesce(func.sum(Withdrawal.amount), Decimal('0'))
    ).filter(
        Withdrawal.creator_id == current_user.id,
        Withdrawal.status == 'pending'
    ).scalar()

    withdrawable = float(Decimal(str(available_balance)) - total_withdrawn - pending_withdrawals)

    if amount > withdrawable:
        flash('Saldo insuficiente para saque.', 'error')
        return redirect(url_for('dashboard.index'))

    # Create withdrawal request
    withdrawal = Withdrawal(
        creator_id=current_user.id,
        amount=amount,
        pix_key=pix_key,
        status='pending'
    )
    db.session.add(withdrawal)
    db.session.commit()

    # Invalidar cache do saldo após saque
    cache.delete_memoized(calculate_balance, current_user.id)

    flash(f'Saque de R$ {amount:.2f} solicitado com sucesso! Será processado em até 3 dias úteis.', 'success')
    return redirect(url_for('dashboard.index'))

# Substitua a função profile() no arquivo app/routes/dashboard.py por esta versão:

@bp.route('/profile')
@login_required
def profile():
    """Perfil do criador"""
    effective = get_effective_creator()

    # Calcular estatísticas do usuário
    total_earned = db.session.query(func.sum(Transaction.amount)).join(
        Subscription
    ).join(
        Group
    ).filter(
        Group.creator_id == effective.id,
        Transaction.status == 'completed'
    ).scalar() or 0

    # Total de assinantes ativos
    total_subscribers = db.session.query(func.count(Subscription.id)).join(
        Group
    ).filter(
        Group.creator_id == effective.id,
        Subscription.status == 'active'
    ).scalar() or 0

    # Total de grupos
    total_groups = Group.query.filter_by(creator_id=effective.id).count()

    # Total sacado
    total_withdrawn = 0

    # Calcular saldo disponível
    balance = total_earned - total_withdrawn

    # Data de cadastro formatada
    member_since = effective.created_at.strftime('%d/%m/%Y') if effective.created_at else 'N/A'

    # Buscar transações recentes
    recent_transactions = Transaction.query.join(
        Subscription
    ).join(
        Group
    ).filter(
        Group.creator_id == effective.id
    ).order_by(
        Transaction.created_at.desc()
    ).limit(10).all()

    # Preparar dados das estatísticas
    stats = {
        'total_earned': total_earned,
        'balance': balance,
        'total_withdrawn': total_withdrawn,
        'total_groups': total_groups,
        'total_subscribers': total_subscribers,
        'member_since': member_since
    }

    return render_template('dashboard/profile.html',
        user=effective,
        stats=stats,
        recent_transactions=recent_transactions,
        has_password=bool(effective.password_hash)
    )


@bp.route('/profile/reset-password', methods=['POST'])
@login_required
@limiter.limit("3 per hour")
def profile_reset_password():
    """Enviar email de redefinição de senha para o usuário logado"""
    if is_admin_viewing():
        flash('Acao nao permitida no modo admin.', 'warning')
        return redirect(url_for('dashboard.profile'))

    if not current_user.password_hash:
        flash('Sua conta não possui senha. Use o formulário acima para definir uma.', 'info')
        return redirect(url_for('dashboard.profile'))

    token = generate_reset_token(current_user.id, password_hash=current_user.password_hash)
    try:
        send_password_reset_email(current_user, token)
        flash('Email de redefinição de senha enviado! Verifique sua caixa de entrada.', 'success')
    except Exception:
        logger.error("Failed to send password reset email from profile", exc_info=True)
        flash('Erro ao enviar email. Tente novamente mais tarde.', 'error')

    return redirect(url_for('dashboard.profile'))


@bp.route('/profile/update', methods=['POST'])
@login_required
def update_profile():
    """Atualizar perfil"""
    if is_admin_viewing():
        flash('Acao nao permitida no modo admin.', 'warning')
        return redirect(url_for('dashboard.profile'))

    name = request.form.get('name')
    email = request.form.get('email')
    phone = request.form.get('phone', '').strip()
    pix_key_type = request.form.get('pix_key_type', '').strip()
    pix_key_value = request.form.get('pix_key_value', '').strip()
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')

    # Build new PIX key from type:value
    new_pix_key = None
    if pix_key_type and pix_key_value:
        new_pix_key = f"{pix_key_type}:{pix_key_value}"

    # PIX requires phone for support contact
    if new_pix_key and not phone:
        flash('Informe seu telefone/WhatsApp para cadastrar a chave PIX (necessário para suporte).', 'error')
        return redirect(url_for('dashboard.profile'))

    # Check if PIX key is being changed
    changing_pix = new_pix_key != current_user.pix_key

    # Check if sensitive changes are being made (email, password, or PIX)
    changing_email = email and email != current_user.email
    changing_password = bool(new_password)

    is_oauth_only = not current_user.password_hash
    if changing_email or changing_password or changing_pix:
        if is_oauth_only and changing_password and not changing_email and not changing_pix:
            # OAuth-only user definindo senha pela primeira vez — não exigir senha atual
            pass
        else:
            if not current_password:
                flash('Informe a senha atual para alterar email, senha ou chave PIX', 'error')
                return redirect(url_for('dashboard.profile'))
            if not current_user.check_password(current_password):
                flash('Senha atual incorreta', 'error')
                return redirect(url_for('dashboard.profile'))

    # Process password change
    if changing_password:
        if new_password != confirm_password:
            flash('As novas senhas não coincidem', 'error')
            return redirect(url_for('dashboard.profile'))
        if len(new_password) < 8:
            flash('A nova senha deve ter no mínimo 8 caracteres', 'error')
            return redirect(url_for('dashboard.profile'))
        if not any(c.isupper() for c in new_password):
            flash('A nova senha deve conter pelo menos uma letra maiúscula', 'error')
            return redirect(url_for('dashboard.profile'))
        if not any(c.isdigit() for c in new_password):
            flash('A nova senha deve conter pelo menos um número', 'error')
            return redirect(url_for('dashboard.profile'))
        current_user.set_password(new_password)

    # Update name (no password required)
    if name:
        current_user.name = name

    # Update email (password already verified above)
    if changing_email:
        if Creator.query.filter_by(email=email).first():
            flash('Este email já está em uso', 'error')
            return redirect(url_for('dashboard.profile'))
        current_user.email = email

    # Update PIX key (password already verified above)
    if changing_pix:
        current_user.pix_key = new_pix_key

    # Update phone (no password required)
    if phone is not None:
        current_user.phone = phone

    db.session.commit()
    flash('Perfil atualizado com sucesso!', 'success')

    return redirect(url_for('dashboard.profile'))


@bp.route('/profile/delete', methods=['POST'])
@login_required
@limiter.limit("3 per hour")
def delete_account():
    """Excluir conta (LGPD) - soft delete com anonimização"""
    if is_admin_viewing():
        flash('Acao nao permitida no modo admin.', 'warning')
        return redirect(url_for('dashboard.profile'))

    from flask_login import logout_user

    password = request.form.get('password')
    confirmation = request.form.get('confirmation')

    if confirmation != 'EXCLUIR':
        flash('Confirmação inválida. Digite EXCLUIR para confirmar.', 'error')
        return redirect(url_for('dashboard.profile'))

    if not password or not current_user.check_password(password):
        flash('Senha incorreta.', 'error')
        return redirect(url_for('dashboard.profile'))

    # Soft delete: deactivate and anonymize personal data
    creator = Creator.query.get(current_user.id)
    creator.is_active = False
    creator.name = 'Conta Excluída'
    creator.email = f'deleted_{creator.id}@removed'
    creator.username = f'deleted_{creator.id}'
    creator.pix_key = None
    creator.phone = None
    creator.telegram_username = None

    db.session.commit()

    logout_user()
    flash('Sua conta foi excluída com sucesso.', 'info')
    return redirect(url_for('main.index'))


@bp.route('/analytics')
@login_required
def analytics():
    """Analytics avançado - versão corrigida"""
    effective = get_effective_creator()
    from datetime import datetime, timedelta, date
    from sqlalchemy import func, desc

    # Período selecionado
    period = request.args.get('period', '30')
    days = int(period) if period in ['7', '30', '90'] else 30

    # Usar utcnow() pois created_at no banco usa UTC
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    # Buscar grupos
    groups = Group.query.filter_by(creator_id=effective.id).all()

    # Estatísticas gerais
    total_revenue = db.session.query(func.sum(Transaction.amount)).join(
        Subscription
    ).join(
        Group
    ).filter(
        Group.creator_id == effective.id,
        Transaction.status == 'completed',
        Transaction.created_at >= start_date,
        Transaction.created_at <= end_date
    ).scalar() or 0

    total_transactions = Transaction.query.join(
        Subscription
    ).join(
        Group
    ).filter(
        Group.creator_id == effective.id,
        Transaction.status == 'completed',
        Transaction.created_at >= start_date,
        Transaction.created_at <= end_date
    ).count()

    average_ticket = float(total_revenue) / total_transactions if total_transactions > 0 else 0

    total_subscribers = Subscription.query.join(
        Group
    ).filter(
        Group.creator_id == effective.id,
        Subscription.status == 'active'
    ).count()

    new_subscribers = Subscription.query.join(
        Group
    ).filter(
        Group.creator_id == effective.id,
        Subscription.created_at >= start_date,
        Subscription.created_at <= end_date
    ).count()
    
    # Preparar labels
    revenue_labels = []
    revenue_data = []
    subscribers_labels = []
    subscribers_data = []
    
    # Gerar lista de datas
    date_list = []
    current_date = start_date.date()
    while current_date <= end_date.date():
        date_list.append(current_date)
        revenue_labels.append(current_date.strftime('%d/%m'))
        current_date += timedelta(days=1)
    
    subscribers_labels = revenue_labels.copy()
    
    # 1. Buscar receita por dia
    daily_revenue = db.session.query(
        func.date(Transaction.created_at).label('date'),
        func.sum(Transaction.amount).label('total')
    ).join(
        Subscription
    ).join(
        Group
    ).filter(
        Group.creator_id == effective.id,
        Transaction.status == 'completed',
        func.date(Transaction.created_at) >= start_date.date(),
        func.date(Transaction.created_at) <= end_date.date()
    ).group_by(
        func.date(Transaction.created_at)
    ).all()
    
    # Converter para dicionário
    revenue_dict = {}
    for r in daily_revenue:
        # Garantir que estamos comparando objetos date
        if isinstance(r.date, str):
            date_obj = datetime.strptime(r.date, '%Y-%m-%d').date()
        else:
            date_obj = r.date
        
        revenue_dict[date_obj] = float(r.total)
    
    # Preencher dados
    for date_obj in date_list:
        value = revenue_dict.get(date_obj, 0.0)
        revenue_data.append(value)
    
    # 2. Buscar assinantes por dia
    daily_subscribers = db.session.query(
        func.date(Subscription.created_at).label('date'),
        func.count(Subscription.id).label('count')
    ).join(
        Group
    ).filter(
        Group.creator_id == effective.id,
        func.date(Subscription.created_at) >= start_date.date(),
        func.date(Subscription.created_at) <= end_date.date()
    ).group_by(
        func.date(Subscription.created_at)
    ).all()
    
    # Converter para dicionário
    subscribers_dict = {}
    for s in daily_subscribers:
        if isinstance(s.date, str):
            date_obj = datetime.strptime(s.date, '%Y-%m-%d').date()
        else:
            date_obj = s.date
        subscribers_dict[date_obj] = s.count
    
    # Preencher dados
    for date_obj in date_list:
        subscribers_data.append(subscribers_dict.get(date_obj, 0))
    
    # 2b. Churn metrics
    churned_subs = Subscription.query.join(Group).filter(
        Group.creator_id == effective.id,
        Subscription.status.in_(['expired', 'cancelled']),
        Subscription.end_date >= start_date,
        Subscription.end_date <= end_date
    ).count()

    active_at_start = Subscription.query.join(Group).filter(
        Group.creator_id == effective.id,
        Subscription.start_date < start_date,
        Subscription.end_date >= start_date
    ).count()

    churn_denominator = active_at_start + new_subscribers
    churn_rate = (churned_subs / churn_denominator * 100) if churn_denominator > 0 else 0

    at_risk = Subscription.query.join(Group).filter(
        Group.creator_id == effective.id,
        Subscription.status == 'active',
        Subscription.end_date <= end_date + timedelta(days=7),
        Subscription.end_date >= end_date,
        or_(
            Subscription.cancel_at_period_end == True,
            Subscription.auto_renew == False
        )
    ).count()

    avg_duration_result = db.session.query(
        func.avg(
            func.extract('epoch', Subscription.end_date) - func.extract('epoch', Subscription.start_date)
        )
    ).join(Group).filter(
        Group.creator_id == effective.id,
        Subscription.status.in_(['expired', 'cancelled']),
        Subscription.end_date >= start_date,
        Subscription.end_date <= end_date
    ).scalar()

    avg_duration = round(float(avg_duration_result) / 86400, 1) if avg_duration_result else 0

    # Daily churn for chart
    daily_churn = db.session.query(
        func.date(Subscription.end_date).label('date'),
        func.count(Subscription.id).label('count')
    ).join(Group).filter(
        Group.creator_id == effective.id,
        Subscription.status.in_(['expired', 'cancelled']),
        func.date(Subscription.end_date) >= start_date.date(),
        func.date(Subscription.end_date) <= end_date.date()
    ).group_by(
        func.date(Subscription.end_date)
    ).all()

    churn_dict = {}
    for c in daily_churn:
        if isinstance(c.date, str):
            date_obj = datetime.strptime(c.date, '%Y-%m-%d').date()
        else:
            date_obj = c.date
        churn_dict[date_obj] = c.count

    churn_data = []
    for date_obj in date_list:
        churn_data.append(churn_dict.get(date_obj, 0))

    # Churn by group for performance table
    churn_by_group_query = db.session.query(
        Subscription.group_id,
        func.count(Subscription.id).label('count')
    ).join(Group).filter(
        Group.creator_id == effective.id,
        Subscription.status.in_(['expired', 'cancelled']),
        Subscription.end_date >= start_date,
        Subscription.end_date <= end_date
    ).group_by(
        Subscription.group_id
    ).all()

    churn_by_group = {row.group_id: row.count for row in churn_by_group_query}

    # 3. Receita por grupo
    group_revenue = db.session.query(
        Group.name,
        func.sum(Transaction.amount).label('total')
    ).select_from(
        Group
    ).join(
        Subscription, Group.id == Subscription.group_id
    ).join(
        Transaction, Transaction.subscription_id == Subscription.id
    ).filter(
        Group.creator_id == effective.id,
        Transaction.status == 'completed',
        Transaction.created_at >= start_date,
        Transaction.created_at <= end_date
    ).group_by(
        Group.id, Group.name
    ).order_by(
        desc('total')
    ).limit(5).all()
    
    group_labels = []
    group_data = []
    for g in group_revenue:
        group_labels.append(g.name)
        group_data.append(float(g.total))
    
    # 4. Receita por plano
    plan_revenue = db.session.query(
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
    ).filter(
        Group.creator_id == effective.id,
        Transaction.status == 'completed',
        Transaction.created_at >= start_date,
        Transaction.created_at <= end_date
    ).group_by(
        PricingPlan.id, PricingPlan.name
    ).all()
    
    plan_labels = []
    plan_data = []
    for p in plan_revenue:
        plan_labels.append(p.name)
        plan_data.append(float(p.total))
    
    # 5. Performance por grupo
    for group in groups:
        group.total_subscribers = Subscription.query.filter_by(
            group_id=group.id,
            status='active'
        ).count()
        
        group_period_revenue = db.session.query(
            func.sum(Transaction.amount)
        ).join(
            Subscription
        ).filter(
            Subscription.group_id == group.id,
            Transaction.status == 'completed',
            Transaction.created_at >= start_date,
            Transaction.created_at <= end_date
        ).scalar() or 0
        
        group.period_revenue = float(group_period_revenue)
        
        group_transactions = Transaction.query.join(
            Subscription
        ).filter(
            Subscription.group_id == group.id,
            Transaction.status == 'completed',
            Transaction.created_at >= start_date,
            Transaction.created_at <= end_date
        ).count()
        
        group.average_ticket = float(group_period_revenue) / group_transactions if group_transactions > 0 else 0
        group.churned = churn_by_group.get(group.id, 0)

    # Preparar dados finais
    stats = {
        'total_revenue': float(total_revenue),
        'total_transactions': total_transactions,
        'average_ticket': average_ticket,
        'total_subscribers': total_subscribers,
        'new_subscribers': new_subscribers,
        'churned_subs': churned_subs,
        'churn_rate': round(churn_rate, 1),
        'at_risk': at_risk,
        'avg_duration': avg_duration
    }
    
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
            'labels': group_labels if group_labels else ['Sem dados'],
            'data': group_data if group_data else [0]
        },
        'revenue_by_plan': {
            'labels': plan_labels if plan_labels else ['Sem dados'],
            'data': plan_data if plan_data else [0]
        },
        'churn_by_day': {
            'labels': revenue_labels,
            'data': churn_data
        }
    }
    
    return render_template(
        'dashboard/analytics.html',
        stats=stats,
        period=period,
        groups=groups,
        charts_data=charts_data
    )