# app/routes/groups.py
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, Response, session
from flask_login import login_required, current_user
from app import db
from app.models import Group, PricingPlan, Subscription, Transaction
from datetime import datetime, timedelta
from sqlalchemy import func
import requests
import os
import csv
from io import StringIO

bp = Blueprint('groups', __name__, url_prefix='/groups')

@bp.route('/')
@login_required
def list():
    """Lista todos os grupos do criador"""
    groups = current_user.groups.all()
    
    # Atualizar contador de assinantes para cada grupo
    for group in groups:
        group.total_subscribers = Subscription.query.filter_by(
            group_id=group.id,
            status='active'
        ).count()
        
        # Calcular receita total do grupo
        group.total_revenue = db.session.query(func.sum(Transaction.amount)).join(
            Subscription
        ).filter(
            Subscription.group_id == group.id,
            Transaction.status == 'completed'
        ).scalar() or 0
    
    return render_template('dashboard/groups.html', groups=groups)

@bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Criar novo grupo"""
    if request.method == 'POST':
        # Dados básicos do grupo
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        telegram_id = request.form.get('telegram_id', '').strip()
        invite_link = request.form.get('invite_link', '').strip()
        
        # Verificar se deve validar no Telegram
        skip_validation = request.form.get('skip_validation') == 'on'
        
        # Se marcar para pular validação, criar direto
        if skip_validation:
            pass
        else:
            # Tentar validar
            bot_token = os.getenv('BOT_TOKEN') or os.getenv('TELEGRAM_BOT_TOKEN')
            
            if bot_token and telegram_id:
                try:
                    # URL da API
                    url = f"https://api.telegram.org/bot{bot_token}/getChat"
                    
                    # Fazer requisição
                    response = requests.get(
                        url,
                        params={"chat_id": telegram_id},
                        timeout=10
                    )
                    
                    if response.status_code != 200:
                        flash('❌ Erro ao conectar com o Telegram. Use "Pular validação" para continuar.', 'error')
                        return render_template('dashboard/group_form.html', 
                                             group=None,
                                             show_success_modal=False)
                    
                    # Processar resposta
                    try:
                        data = response.json()
                    except Exception as json_error:
                        flash('❌ Resposta inválida do Telegram. Use "Pular validação".', 'error')
                        return render_template('dashboard/group_form.html', 
                                             group=None,
                                             show_success_modal=False)
                    
                    if not data.get('ok'):
                        error_msg = data.get('description', 'Erro desconhecido')
                        flash(f'❌ Telegram: {error_msg}', 'error')
                        return render_template('dashboard/group_form.html', 
                                             group=None,
                                             show_success_modal=False)
                    
                    # Grupo encontrado!
                    chat = data.get('result', {})
                    
                    # Verificar se o bot é admin
                    bot_id = bot_token.split(':')[0]
                    bot_member = requests.get(
                        f"https://api.telegram.org/bot{bot_token}/getChatMember",
                        params={
                            "chat_id": telegram_id,
                            "user_id": bot_id
                        },
                        timeout=10
                    )
                    
                    if bot_member.status_code == 200:
                        member_data = bot_member.json()
                        if member_data.get('ok'):
                            status = member_data.get('result', {}).get('status')
                            if status not in ['administrator', 'creator']:
                                flash('⚠️ O bot precisa ser administrador do grupo!', 'warning')
                                return render_template('dashboard/group_form.html', 
                                                     group=None,
                                                     show_success_modal=False)
                    
                except requests.exceptions.RequestException as req_error:
                    flash(f'❌ Erro de conexão: {req_error}. Use "Pular validação".', 'error')
                    return render_template('dashboard/group_form.html', 
                                         group=None,
                                         show_success_modal=False)
                except Exception as e:
                    flash(f'Erro: {e}. Use "Pular validacao".', 'error')
                    return render_template('dashboard/group_form.html', 
                                         group=None,
                                         show_success_modal=False)
            else:
                if not bot_token:
                    flash('Bot nao configurado. Use "Pular validacao".', 'warning')
                else:
                    flash('⚠️ ID do Telegram não fornecido.', 'warning')
        
        # Criar grupo
        group = Group(
            name=name,
            description=description,
            telegram_id=telegram_id,
            invite_link=invite_link,
            creator_id=current_user.id,
            is_active=True
        )
        
        db.session.add(group)
        db.session.commit()
        
        # Adicionar planos
        plan_names = request.form.getlist('plan_name[]')
        plan_durations = request.form.getlist('plan_duration[]')
        plan_prices = request.form.getlist('plan_price[]')
        
        for i in range(len(plan_names)):
            if plan_names[i]:
                plan = PricingPlan(
                    group_id=group.id,
                    name=plan_names[i],
                    duration_days=int(plan_durations[i]),
                    price=float(plan_prices[i]),
                    is_active=True
                )
                db.session.add(plan)
        
        db.session.commit()
        
        # CORREÇÃO IMPORTANTE: Gerar link do bot usando group.id, não telegram_id
        bot_username = os.getenv('TELEGRAM_BOT_USERNAME') or os.getenv('BOT_USERNAME', 'televipbra_bot')
        bot_link = f"https://t.me/{bot_username}?start=g_{group.id}"  # USAR group.id AQUI!
        
        flash(f'Grupo "{group.name}" criado com sucesso! Link: {bot_link}', 'success')
        
        # Renderizar template com modal de sucesso
        return render_template('dashboard/group_form.html', 
                             group=None,
                             show_success_modal=True,
                             new_group_name=group.name,
                             new_group_id=group.id,  # Passar o ID também
                             new_group_telegram_id=group.telegram_id,
                             bot_link=bot_link)
    
    return render_template('dashboard/group_form.html', 
                         group=None,
                         show_success_modal=False)

@bp.route('/clear-success-modal', methods=['POST'])
@login_required
def clear_success_modal():
    """Limpar flags do modal de sucesso da sessão"""
    session.pop('show_success_modal', None)
    session.pop('new_group_name', None)
    session.pop('new_group_id', None)
    session.pop('new_group_telegram_id', None)
    session.pop('bot_link', None)
    return '', 204

@bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    """Editar grupo existente"""
    group = Group.query.filter_by(id=id, creator_id=current_user.id).first_or_404()
    
    if request.method == 'POST':
        # Atualizar dados básicos
        group.name = request.form.get('name')
        group.description = request.form.get('description')
        group.invite_link = request.form.get('invite_link')
        group.is_active = 'is_active' in request.form
        
        # Remover planos existentes (simplificado - em produção, seria melhor atualizar)
        PricingPlan.query.filter_by(group_id=group.id).delete()
        
        # Adicionar novos planos
        plan_names = request.form.getlist('plan_name[]')
        plan_durations = request.form.getlist('plan_duration[]')
        plan_prices = request.form.getlist('plan_price[]')
        
        for i in range(len(plan_names)):
            if plan_names[i]:
                plan = PricingPlan(
                    group_id=group.id,
                    name=plan_names[i],
                    duration_days=int(plan_durations[i]),
                    price=float(plan_prices[i]),
                    is_active=True
                )
                db.session.add(plan)
        
        db.session.commit()
        flash('Grupo atualizado com sucesso!', 'success')
        return redirect(url_for('groups.list'))
    
    return render_template('dashboard/group_form.html', group=group)

@bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    """Deletar grupo"""
    group = Group.query.filter_by(id=id, creator_id=current_user.id).first_or_404()
    
    # Verificar se há assinaturas ativas
    active_subs = Subscription.query.filter_by(
        group_id=id,
        status='active'
    ).count()
    
    if active_subs > 0:
        flash(f'Não é possível deletar o grupo. Existem {active_subs} assinaturas ativas.', 'error')
        return redirect(url_for('groups.list'))
    
    # Deletar planos e depois o grupo
    PricingPlan.query.filter_by(group_id=id).delete()
    db.session.delete(group)
    db.session.commit()
    
    flash('Grupo deletado com sucesso!', 'success')
    return redirect(url_for('groups.list'))

@bp.route('/<int:id>/toggle', methods=['POST'])
@login_required
def toggle(id):
    """Ativar/Desativar grupo"""
    group = Group.query.filter_by(id=id, creator_id=current_user.id).first_or_404()
    
    group.is_active = not group.is_active
    db.session.commit()
    
    status = 'ativado' if group.is_active else 'desativado'
    flash(f'Grupo {status} com sucesso!', 'success')
    
    return redirect(url_for('groups.list'))

# Adicione esta função no arquivo app/routes/groups.py

@bp.route('/<int:group_id>/broadcast', methods=['GET', 'POST'])
@login_required
def broadcast(group_id):
    """Enviar mensagem para todos os assinantes do grupo"""
    group = Group.query.filter_by(id=group_id, creator_id=current_user.id).first_or_404()
    
    if request.method == 'POST':
        message = request.form.get('message', '').strip()
        
        if not message:
            flash('Por favor, digite uma mensagem.', 'error')
            return redirect(url_for('groups.broadcast', group_id=group_id))
        
        # Buscar assinantes ativos
        active_subs = Subscription.query.filter_by(
            group_id=group_id,
            status='active'
        ).all()
        
        if not active_subs:
            flash('Nenhum assinante ativo para enviar mensagem.', 'warning')
            return redirect(url_for('groups.subscribers', id=group_id))
        
        # Aqui você pode implementar o envio via Telegram Bot API
        # Por enquanto, vamos apenas simular
        sent_count = 0
        failed_count = 0
        
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN') or os.getenv('BOT_TOKEN')
        
        if bot_token:
            for sub in active_subs:
                try:
                    # Enviar mensagem via API do Telegram
                    response = requests.post(
                        f'https://api.telegram.org/bot{bot_token}/sendMessage',
                        json={
                            'chat_id': sub.telegram_user_id,
                            'text': f"📢 **Mensagem de {group.name}**\n\n{message}",
                            'parse_mode': 'Markdown'
                        }
                    )
                    
                    if response.status_code == 200:
                        sent_count += 1
                    else:
                        failed_count += 1
                except:
                    failed_count += 1
        else:
            flash('Bot do Telegram não configurado.', 'error')
            return redirect(url_for('groups.subscribers', id=group_id))
        
        flash(f'Mensagem enviada para {sent_count} assinantes. {failed_count} falharam.', 'success')
        return redirect(url_for('groups.subscribers', id=group_id))
    
    # GET - mostrar formulário
    active_count = Subscription.query.filter_by(
        group_id=group_id,
        status='active'
    ).count()
    
    return render_template('dashboard/broadcast.html',
                         group=group,
                         active_count=active_count)

@bp.route('/<int:id>/subscribers')
@login_required
def subscribers(id):
    """Listar assinantes do grupo"""
    group = Group.query.filter_by(id=id, creator_id=current_user.id).first_or_404()
    
    # Buscar assinantes ativos
    active_subs = Subscription.query.filter_by(
        group_id=id,
        status='active'
    ).order_by(Subscription.end_date.desc()).all()
    
    # Buscar assinantes expirados recentes (últimos 30 dias)
    expired_subs = Subscription.query.filter(
        Subscription.group_id == id,
        Subscription.status == 'expired',
        Subscription.end_date >= datetime.utcnow() - timedelta(days=30)
    ).order_by(Subscription.end_date.desc()).all()
    
    # ADICIONAR ESTATÍSTICAS QUE ESTÃO FALTANDO
    stats = {
        'total': len(active_subs) + len(expired_subs),
        'active': len(active_subs),
        'expired': len(expired_subs),
        'revenue': db.session.query(func.sum(Transaction.amount)).join(
            Subscription
        ).filter(
            Subscription.group_id == id,
            Transaction.status == 'completed'
        ).scalar() or 0
    }
    
    return render_template('dashboard/subscribers.html',
                         group=group,
                         active_subs=active_subs,
                         expired_subs=expired_subs,
                         stats=stats)  # ADICIONAR stats AQUI

@bp.route('/<int:id>/export-subscribers')
@login_required
def export_subscribers(id):
    """Exportar lista de assinantes em CSV"""
    group = Group.query.filter_by(id=id, creator_id=current_user.id).first_or_404()
    
    # Buscar todos os assinantes
    subscribers = Subscription.query.filter_by(group_id=id).all()
    
    # Criar CSV
    output = StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow([
        'Username',
        'Plano',
        'Status',
        'Data Início',
        'Data Fim',
        'Valor Pago'
    ])
    
    # Dados
    for sub in subscribers:
        # Calcular valor total pago
        total_paid = db.session.query(func.sum(Transaction.amount)).filter_by(
            subscription_id=sub.id,
            status='completed'
        ).scalar() or 0
        
        writer.writerow([
            sub.telegram_username or 'N/A',
            sub.plan.name,
            sub.status,
            sub.start_date.strftime('%d/%m/%Y'),
            sub.end_date.strftime('%d/%m/%Y'),
            f'R$ {total_paid:.2f}'
        ])
    
    # Preparar resposta
    output.seek(0)
    response = Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename=assinantes_{group.name}_{datetime.now().strftime("%Y%m%d")}.csv'
        }
    )
    
    return response

@bp.route('/<int:id>/stats')
@login_required
def stats(id):
    """Estatísticas detalhadas do grupo"""
    group = Group.query.filter_by(id=id, creator_id=current_user.id).first_or_404()
    
    # Estatísticas gerais
    stats = {
        'total_subscribers': Subscription.query.filter_by(group_id=id).count(),
        'active_subscribers': Subscription.query.filter_by(group_id=id, status='active').count(),
        'total_revenue': 0,
        'monthly_revenue': 0,
        'avg_subscription_value': 0,
        'churn_rate': 0
    }
    
    # Receita total
    stats['total_revenue'] = db.session.query(func.sum(Transaction.amount)).join(
        Subscription
    ).filter(
        Subscription.group_id == id,
        Transaction.status == 'completed'
    ).scalar() or 0
    
    # Receita do mês atual
    start_of_month = datetime.now().replace(day=1, hour=0, minute=0, second=0)
    stats['monthly_revenue'] = db.session.query(func.sum(Transaction.amount)).join(
        Subscription
    ).filter(
        Subscription.group_id == id,
        Transaction.status == 'completed',
        Transaction.created_at >= start_of_month
    ).scalar() or 0
    
    # Valor médio de assinatura
    if stats['total_subscribers'] > 0:
        stats['avg_subscription_value'] = stats['total_revenue'] / stats['total_subscribers']
    
    # Taxa de cancelamento (churn)
    if stats['total_subscribers'] > 0:
        expired_count = Subscription.query.filter_by(
            group_id=id,
            status='expired'
        ).count()
        stats['churn_rate'] = (expired_count / stats['total_subscribers']) * 100
    
    # Buscar dados para gráficos (últimos 30 dias)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    
    # Receita por dia
    daily_revenue = db.session.query(
        func.date(Transaction.created_at).label('date'),
        func.sum(Transaction.amount).label('revenue')
    ).join(
        Subscription
    ).filter(
        Subscription.group_id == id,
        Transaction.status == 'completed',
        Transaction.created_at >= thirty_days_ago
    ).group_by(
        func.date(Transaction.created_at)
    ).all()
    
    # Novas assinaturas por dia
    daily_subscriptions = db.session.query(
        func.date(Subscription.created_at).label('date'),
        func.count(Subscription.id).label('count')
    ).filter(
        Subscription.group_id == id,
        Subscription.created_at >= thirty_days_ago
    ).group_by(
        func.date(Subscription.created_at)
    ).all()
    
    # Distribuição por plano
    plan_distribution = db.session.query(
        PricingPlan.name,
        func.count(Subscription.id).label('count')
    ).join(
        Subscription
    ).filter(
        Subscription.group_id == id,
        Subscription.status == 'active'
    ).group_by(
        PricingPlan.name
    ).all()
    
    return render_template('dashboard/group_stats.html',
                         group=group,
                         stats=stats,
                         daily_revenue=daily_revenue,
                         daily_subscriptions=daily_subscriptions,
                         plan_distribution=plan_distribution)

@bp.route('/<int:id>/link')
@login_required
def get_link(id):
    """Obter link do bot para o grupo"""
    group = Group.query.filter_by(id=id, creator_id=current_user.id).first_or_404()
    
    # CORREÇÃO: Usar group.id ao invés de telegram_id
    bot_username = os.getenv('TELEGRAM_BOT_USERNAME') or os.getenv('BOT_USERNAME', 'televipbra_bot')
    bot_link = f"https://t.me/{bot_username}?start=g_{group.id}"
    
    return jsonify({
        'success': True,
        'link': bot_link,
        'group_name': group.name
    })