from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_required, current_user, login_user
from app import db
from app.models import Creator, Group, Subscription, Transaction
from app.utils.decorators import admin_required
from datetime import datetime
from sqlalchemy import func

# Tentar importar Withdrawal
try:
    from app.models import Withdrawal
    has_withdrawal_model = True
except ImportError:
    has_withdrawal_model = False
    Withdrawal = None

bp = Blueprint('admin', __name__, url_prefix='/admin')

@bp.route('/')
@login_required
@admin_required
def index():
    """Painel administrativo principal"""
    # Estatísticas gerais
    stats = {
        'total_creators': Creator.query.count(),
        'total_groups': Group.query.count(),
        'total_subscriptions': Subscription.query.filter_by(status='active').count(),
        'pending_withdrawals': 0
    }
    
    # Saques pendentes e total a pagar
    pending_withdrawals = []
    total_to_pay = 0
    
    if has_withdrawal_model and Withdrawal:
        stats['pending_withdrawals'] = Withdrawal.query.filter_by(status='pending').count()
        
        # Buscar saques pendentes ordenados por created_at
        pending_withdrawals = Withdrawal.query.filter_by(status='pending').order_by(
            Withdrawal.created_at.desc()
        ).all()
        
        # Calcular total a pagar
        total_to_pay = sum(w.amount for w in pending_withdrawals)
    
    # Todos os criadores com informações adicionais
    creators = Creator.query.order_by(Creator.created_at.desc()).all()
    
    # Adicionar informações extras para cada criador
    for creator in creators:
        # Total de assinantes ativos
        creator.total_subscribers = db.session.query(func.count(Subscription.id)).join(
            Group
        ).filter(
            Group.creator_id == creator.id,
            Subscription.status == 'active'
        ).scalar() or 0
        
        # Verificar se tem saque pendente
        creator.pending_withdrawal = False
        if has_withdrawal_model and Withdrawal:
            creator.pending_withdrawal = Withdrawal.query.filter_by(
                creator_id=creator.id,
                status='pending'
            ).first() is not None
    
    return render_template('admin/index.html',
                         stats=stats,
                         pending_withdrawals=pending_withdrawals,
                         total_to_pay=total_to_pay,
                         creators=creators)

@bp.route('/withdrawal/<int:id>/process', methods=['POST'])
@login_required
@admin_required
def process_withdrawal(id):
    """Processar saque"""
    if not has_withdrawal_model or not Withdrawal:
        flash('Modelo de saque não disponível!', 'error')
        return redirect(url_for('admin.index'))
    
    withdrawal = Withdrawal.query.get_or_404(id)
    
    if withdrawal.status != 'pending':
        flash('Este saque já foi processado!', 'warning')
        return redirect(url_for('admin.index'))
    
    # Marcar como processado
    withdrawal.status = 'completed'
    withdrawal.processed_at = datetime.utcnow()
    
    # Atualizar saldo do criador
    creator = withdrawal.creator
    creator.balance -= withdrawal.amount
    
    db.session.commit()
    
    flash(f'Saque de R$ {withdrawal.amount:.2f} processado com sucesso!', 'success')
    return redirect(url_for('admin.index'))

@bp.route('/users')
@login_required
@admin_required
def users():
    """Lista de todos os usuários"""
    users = Creator.query.order_by(Creator.created_at.desc()).all()
    return render_template('admin/users.html', users=users)

@bp.route('/creator/<int:creator_id>/dashboard')
@login_required
@admin_required
def view_creator_dashboard(creator_id):
    """Admin visualiza o dashboard de um criador específico"""
    creator = Creator.query.get_or_404(creator_id)
    
    # Salvar o ID do criador atual e o modo admin na sessão
    session['admin_viewing_as'] = creator_id
    session['admin_mode'] = True
    
    # Fazer login temporário como o criador (sem senha)
    login_user(creator, force=True)
    
    flash(f'Você está visualizando o dashboard de {creator.name}. Para voltar ao admin, use o botão no topo.', 'info')
    
    return redirect(url_for('dashboard.index'))

@bp.route('/creator/<int:creator_id>/details')
@login_required
@admin_required
def creator_details(creator_id):
    """Ver detalhes completos de um criador"""
    creator = Creator.query.get_or_404(creator_id)
    
    # Buscar grupos do criador
    groups = creator.groups.all()
    
    # Estatísticas
    stats = {
        'total_groups': len(groups),
        'total_subscribers': 0,
        'active_subscribers': 0,
        'total_revenue': 0,
        'pending_withdrawal': 0
    }
    
    # Calcular estatísticas
    for group in groups:
        stats['total_subscribers'] += Subscription.query.filter_by(group_id=group.id).count()
        stats['active_subscribers'] += Subscription.query.filter_by(
            group_id=group.id,
            status='active'
        ).count()
    
    # Receita total (usando amount ao invés de net_amount)
    stats['total_revenue'] = db.session.query(
        func.sum(Transaction.amount)
    ).join(Subscription).join(Group).filter(
        Group.creator_id == creator_id,
        Transaction.status == 'completed'
    ).scalar() or 0
    
    # Saques pendentes
    pending_withdrawals = []
    if has_withdrawal_model and Withdrawal:
        pending_withdrawals = Withdrawal.query.filter_by(
            creator_id=creator_id,
            status='pending'
        ).all()
        stats['pending_withdrawal'] = sum(w.amount for w in pending_withdrawals)
    
    # Últimas transações
    recent_transactions = Transaction.query.join(
        Subscription
    ).join(Group).filter(
        Group.creator_id == creator_id
    ).order_by(Transaction.created_at.desc()).limit(10).all()
    
    return render_template('admin/creator_details.html',
                         creator=creator,
                         groups=groups,
                         stats=stats,
                         recent_transactions=recent_transactions,
                         pending_withdrawals=pending_withdrawals)

@bp.route('/creator/<int:creator_id>/message', methods=['POST'])
@login_required
@admin_required
def send_creator_message(creator_id):
    """Enviar mensagem para um criador"""
    creator = Creator.query.get_or_404(creator_id)
    
    subject = request.form.get('subject')
    message = request.form.get('message')
    
    # Aqui você implementaria o envio de email ou notificação
    # Por enquanto, apenas simulamos
    
    flash(f'Mensagem enviada para {creator.name}!', 'success')
    return redirect(url_for('admin.index'))

@bp.route('/exit-creator-view')
@login_required
def exit_creator_view():
    """Sair da visualização do criador e voltar ao admin"""
    if 'admin_viewing_as' in session:
        # Limpar sessão
        session.pop('admin_viewing_as', None)
        session.pop('admin_mode', None)
        
        # Fazer login como admin novamente
        admin_email = current_user.email  # Salvar email antes
        admin = Creator.query.filter_by(email='mauro_lcf@example.com').first()
        if not admin:
            admin = Creator.query.filter_by(email='admin@televip.com').first()
        
        if admin:
            login_user(admin, force=True)
        
        flash('Você voltou ao painel administrativo.', 'info')
    
    return redirect(url_for('admin.index'))