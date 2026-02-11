from flask import Blueprint, render_template, redirect, url_for, flash, request, session, jsonify
from flask_login import login_required, current_user
from app import db
from app.models import Creator, Group, Subscription, Transaction
from app.utils.decorators import admin_required
from datetime import datetime, timedelta
from sqlalchemy import func
import requests as http_requests
import os
import logging

logger = logging.getLogger(__name__)

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

        # Calcular total ganho real a partir das transações completadas
        real_total_earned = db.session.query(
            func.coalesce(func.sum(Transaction.net_amount), 0)
        ).join(Subscription).join(Group).filter(
            Group.creator_id == creator.id,
            Transaction.status == 'completed'
        ).scalar() or 0

        # Calcular total já sacado
        total_withdrawn = 0
        if has_withdrawal_model and Withdrawal:
            total_withdrawn = db.session.query(
                func.coalesce(func.sum(Withdrawal.amount), 0)
            ).filter(
                Withdrawal.creator_id == creator.id,
                Withdrawal.status == 'completed'
            ).scalar() or 0

        # Usar atributos temporários para exibição (não persistem no DB)
        creator.display_total_earned = real_total_earned
        creator.display_balance = real_total_earned - total_withdrawn

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
    """Processar saque com row locking para evitar race condition"""
    if not has_withdrawal_model or not Withdrawal:
        flash('Modelo de saque não disponível!', 'error')
        return redirect(url_for('admin.index'))

    try:
        # Row lock: SELECT ... FOR UPDATE to prevent concurrent processing
        withdrawal = Withdrawal.query.filter_by(id=id).with_for_update().first_or_404()

        # Re-verify status after acquiring lock
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
    except Exception:
        db.session.rollback()
        flash('Erro ao processar saque. Tente novamente.', 'error')

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
    """Admin entra no modo de visualizacao do criador"""
    creator = Creator.query.get_or_404(creator_id)
    session['admin_viewing_id'] = creator.id
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

@bp.route('/creator/<int:creator_id>/block', methods=['POST'])
@login_required
@admin_required
def block_creator(creator_id):
    """Bloquear conta de um criador"""
    creator = Creator.query.get_or_404(creator_id)
    creator.is_blocked = True
    db.session.commit()
    flash(f'Criador {creator.name} foi bloqueado.', 'warning')
    return redirect(url_for('admin.index'))


@bp.route('/creator/<int:creator_id>/unblock', methods=['POST'])
@login_required
@admin_required
def unblock_creator(creator_id):
    """Desbloquear conta de um criador"""
    creator = Creator.query.get_or_404(creator_id)
    creator.is_blocked = False
    db.session.commit()
    flash(f'Criador {creator.name} foi desbloqueado.', 'success')
    return redirect(url_for('admin.index'))


@bp.route('/creator/<int:creator_id>/investigate', methods=['POST'])
@login_required
@admin_required
def investigate_creator(creator_id):
    """Gerar links de convite para investigador infiltrar grupos do criador"""
    creator = Creator.query.get_or_404(creator_id)

    investigator_user_id = request.form.get('investigator_user_id', '').strip()
    if not investigator_user_id or not investigator_user_id.isdigit():
        return jsonify({'error': 'Telegram User ID inválido. Deve ser numérico.'}), 400

    bot_token = os.getenv('BOT_TOKEN') or os.getenv('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        return jsonify({'error': 'BOT_TOKEN não configurado no servidor.'}), 500

    groups = creator.groups.all()
    if not groups:
        return jsonify({'error': f'Criador {creator.name} não possui grupos cadastrados.'}), 404

    results = []
    for group in groups:
        if not group.telegram_id:
            results.append({
                'group_name': group.name,
                'status': 'skipped',
                'message': 'Grupo sem Telegram ID'
            })
            continue

        # Safety net: unban investigator in case they were previously removed
        try:
            http_requests.post(
                f'https://api.telegram.org/bot{bot_token}/unbanChatMember',
                json={
                    'chat_id': group.telegram_id,
                    'user_id': int(investigator_user_id),
                    'only_if_banned': True
                },
                timeout=10
            )
        except Exception as e:
            logger.warning(f'unbanChatMember failed for group {group.telegram_id}: {e}')

        # Generate single-use invite link (expires in 7 days, no name for anonymity)
        try:
            response = http_requests.post(
                f'https://api.telegram.org/bot{bot_token}/createChatInviteLink',
                json={
                    'chat_id': group.telegram_id,
                    'member_limit': 1,
                    'expire_date': int((datetime.utcnow() + timedelta(days=7)).timestamp())
                },
                timeout=10
            )
            data = response.json()

            if data.get('ok'):
                invite_link = data['result']['invite_link']
                results.append({
                    'group_name': group.name,
                    'status': 'success',
                    'invite_link': invite_link
                })
            else:
                error_desc = data.get('description', 'Erro desconhecido')
                logger.error(f'createChatInviteLink failed for group {group.telegram_id}: {error_desc}')
                results.append({
                    'group_name': group.name,
                    'status': 'error',
                    'message': error_desc
                })
        except Exception as e:
            logger.error(f'createChatInviteLink exception for group {group.telegram_id}: {e}')
            results.append({
                'group_name': group.name,
                'status': 'error',
                'message': str(e)
            })

    return jsonify({
        'creator_name': creator.name,
        'investigator_user_id': investigator_user_id,
        'results': results
    })


@bp.route('/exit-creator-view')
@login_required
@admin_required
def exit_creator_view():
    """Sair do modo de visualizacao e voltar ao painel admin"""
    session.pop('admin_viewing_id', None)
    return redirect(url_for('admin.index'))