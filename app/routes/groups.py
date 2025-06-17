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
        
        # Debug: imprimir dados recebidos
        print(f"\n🔍 DEBUG - Dados recebidos:")
        print(f"   Nome: {name}")
        print(f"   Telegram ID: {telegram_id}")
        print(f"   Skip validation: {request.form.get('skip_validation')}")
        
        # Verificar se deve validar no Telegram
        skip_validation = request.form.get('skip_validation') == 'on'
        
        # Se marcar para pular validação, criar direto
        if skip_validation:
            print("⚠️ Pulando validação do Telegram...")
        else:
            # Tentar validar
            bot_token = os.getenv('BOT_TOKEN')
            print(f"\n🔍 DEBUG - BOT_TOKEN existe: {bool(bot_token)}")
            
            if bot_token and telegram_id:
                try:
                    print(f"📡 Tentando verificar grupo {telegram_id}...")
                    
                    # URL da API
                    url = f"https://api.telegram.org/bot{bot_token}/getChat"
                    print(f"📡 URL: {url[:50]}...")
                    
                    # Fazer requisição
                    response = requests.get(
                        url,
                        params={"chat_id": telegram_id},
                        timeout=10
                    )
                    
                    print(f"📡 Status Code: {response.status_code}")
                    
                    if response.status_code != 200:
                        print(f"❌ Resposta não-200: {response.text}")
                        flash('❌ Erro ao conectar com o Telegram. Use "Pular validação" para continuar.', 'error')
                        return render_template('dashboard/group_form.html', 
                                             group=None,
                                             show_success_modal=False)
                    
                    # Processar resposta
                    try:
                        data = response.json()
                        print(f"📡 Resposta JSON: {data}")
                    except Exception as json_error:
                        print(f"❌ Erro ao decodificar JSON: {json_error}")
                        flash('❌ Resposta inválida do Telegram. Use "Pular validação".', 'error')
                        return render_template('dashboard/group_form.html', 
                                             group=None,
                                             show_success_modal=False)
                    
                    if not data.get('ok'):
                        error_msg = data.get('description', 'Erro desconhecido')
                        print(f"❌ API retornou erro: {error_msg}")
                        flash(f'❌ Telegram: {error_msg}', 'error')
                        return render_template('dashboard/group_form.html', 
                                             group=None,
                                             show_success_modal=False)
                    
                    # Grupo encontrado!
                    chat = data.get('result', {})
                    print(f"✅ Grupo encontrado: {chat.get('title')}")
                    
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
                    print(f"❌ Erro de requisição: {type(req_error).__name__}: {req_error}")
                    flash(f'❌ Erro de conexão: {req_error}. Use "Pular validação".', 'error')
                    return render_template('dashboard/group_form.html', 
                                         group=None,
                                         show_success_modal=False)
                except Exception as e:
                    import traceback
                    print(f"❌ Erro inesperado: {type(e).__name__}: {e}")
                    print("Traceback completo:")
                    traceback.print_exc()
                    
                    flash(f'❌ Erro: {e}. Use "Pular validação".', 'error')
                    return render_template('dashboard/group_form.html', 
                                         group=None,
                                         show_success_modal=False)
            else:
                if not bot_token:
                    print("⚠️ BOT_TOKEN não configurado!")
                    flash('⚠️ Bot não configurado. Use "Pular validação".', 'warning')
                else:
                    print("⚠️ Telegram ID não fornecido!")
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
        print(f"✅ Grupo criado com sucesso! ID: {group.id}")
        
        # Gerar link do bot
        bot_username = os.getenv('BOT_USERNAME', 'televipbra_bot')
        bot_link = f"https://t.me/{bot_username}?start=g_{group.telegram_id}"
        
        flash(f'Grupo "{group.name}" criado com sucesso!', 'success')
        
        # Renderizar template com modal de sucesso
        return render_template('dashboard/group_form.html', 
                             group=None,
                             show_success_modal=True,
                             new_group_name=group.name,
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
        return redirect(url_for('groups.edit', id=group.id))
    
    return render_template('dashboard/group_form.html', 
                         group=group,
                         show_success_modal=False)

@bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    """Deletar grupo"""
    group = Group.query.filter_by(id=id, creator_id=current_user.id).first_or_404()
    
    # Verificar se há assinantes ativos
    active_subs = Subscription.query.filter_by(
        group_id=id,
        status='active'
    ).count()
    
    if active_subs > 0:
        flash('Não é possível deletar um grupo com assinantes ativos!', 'error')
    else:
        db.session.delete(group)
        db.session.commit()
        flash('Grupo deletado com sucesso!', 'success')
    
    return redirect(url_for('groups.list'))

@bp.route('/<int:id>/toggle-status', methods=['POST'])
@login_required
def toggle_status(id):
    """Ativar/Desativar grupo"""
    group = Group.query.filter_by(id=id, creator_id=current_user.id).first_or_404()
    
    group.is_active = not group.is_active
    db.session.commit()
    
    status = 'ativado' if group.is_active else 'desativado'
    flash(f'Grupo {status} com sucesso!', 'success')
    
    return redirect(url_for('groups.list'))

@bp.route('/<int:id>/subscribers')
@login_required
def subscribers(id):
    """Ver assinantes do grupo"""
    group = Group.query.filter_by(id=id, creator_id=current_user.id).first_or_404()
    
    # Filtros
    status = request.args.get('status', '')
    plan_id = request.args.get('plan_id', type=int)
    search = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # Query base
    query = Subscription.query.filter_by(group_id=id)
    
    # Aplicar filtros
    if status:
        query = query.filter_by(status=status)
    if plan_id:
        query = query.filter_by(plan_id=plan_id)
    if search:
        query = query.filter(
            db.or_(
                Subscription.telegram_username.contains(search),
                Subscription.telegram_user_id.contains(search)
            )
        )
    
    # Ordenar por data de criação
    query = query.order_by(Subscription.created_at.desc())
    
    # Paginar
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    subscribers = pagination.items
    total_pages = pagination.pages
    
    # Estatísticas
    stats = {
        'total': Subscription.query.filter_by(group_id=id).count(),
        'active': Subscription.query.filter_by(group_id=id, status='active').count(),
        'expired': Subscription.query.filter_by(group_id=id, status='expired').count(),
        'expiring_soon': 0  # Calcular assinaturas expirando em 7 dias
    }
    
    # Calcular expirados em breve
    seven_days_later = datetime.utcnow() + timedelta(days=7)
    stats['expiring_soon'] = Subscription.query.filter(
        Subscription.group_id == id,
        Subscription.status == 'active',
        Subscription.end_date <= seven_days_later,
        Subscription.end_date > datetime.utcnow()
    ).count()
    
    return render_template('dashboard/subscribers.html',
                         group=group,
                         subscribers=subscribers,
                         stats=stats,
                         page=page,
                         total_pages=total_pages,
                         now=datetime.utcnow())

@bp.route('/<int:group_id>/subscribers/<int:sub_id>/cancel', methods=['POST'])
@login_required
def cancel_subscription(group_id, sub_id):
    """Cancelar assinatura de um usuário"""
    group = Group.query.filter_by(id=group_id, creator_id=current_user.id).first_or_404()
    subscription = Subscription.query.filter_by(id=sub_id, group_id=group_id).first_or_404()
    
    subscription.status = 'cancelled'
    db.session.commit()
    
    flash(f'Assinatura de @{subscription.telegram_username} cancelada!', 'success')
    return redirect(url_for('groups.subscribers', id=group_id))

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
    
    # Cabeçalho
    writer.writerow(['Username', 'User ID', 'Plano', 'Status', 'Início', 'Expira em', 'Valor Pago'])
    
    # Dados
    for sub in subscribers:
        writer.writerow([
            f"@{sub.telegram_username}" if sub.telegram_username else 'Sem username',
            sub.telegram_user_id,
            sub.plan.name,
            sub.status,
            sub.start_date.strftime('%d/%m/%Y'),
            sub.end_date.strftime('%d/%m/%Y'),
            f"R$ {sub.plan.price:.2f}"
        ])
    
    # Preparar resposta
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename=assinantes_{group.name}_{datetime.now().strftime("%Y%m%d")}.csv'
        }
    )

@bp.route('/<int:group_id>/subscribers/<int:sub_id>/details')
@login_required
def subscriber_details(group_id, sub_id):
    """Ver detalhes de um assinante via AJAX"""
    group = Group.query.filter_by(id=group_id, creator_id=current_user.id).first_or_404()
    subscription = Subscription.query.filter_by(id=sub_id, group_id=group_id).first_or_404()
    
    # Buscar histórico de transações
    transactions = subscription.transactions.order_by(Transaction.created_at.desc()).all()
    
    return render_template('dashboard/subscriber_modal.html',
                         subscription=subscription,
                         transactions=transactions)

@bp.route('/<int:group_id>/broadcast', methods=['GET', 'POST'])
@login_required
def broadcast(group_id):
    """Enviar mensagem para todos os assinantes do grupo"""
    group = Group.query.filter_by(id=group_id, creator_id=current_user.id).first_or_404()
    
    if request.method == 'POST':
        message = request.form.get('message')
        target = request.form.get('target', 'all')  # all, active, expiring
        
        # Aqui você implementaria o envio real via bot
        # Por enquanto, apenas simular
        
        flash(f'Mensagem enviada para os assinantes do grupo {group.name}!', 'success')
        return redirect(url_for('groups.subscribers', id=group_id))
    
    # Contar destinatários
    active_count = Subscription.query.filter_by(
        group_id=group_id,
        status='active'
    ).count()
    
    return render_template('dashboard/broadcast_form.html',
                         group=group,
                         active_count=active_count)

@bp.route('/<int:id>/stats')
@login_required
def stats(id):
    """Estatísticas detalhadas do grupo"""
    group = Group.query.filter_by(id=id, creator_id=current_user.id).first_or_404()
    
    # Implementar estatísticas detalhadas
    # Por enquanto, redirecionar para assinantes
    return redirect(url_for('groups.subscribers', id=id))

# Adicionar imports necessários no topo do arquivo
from sqlalchemy import func