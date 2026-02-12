"""
Comandos administrativos para criadores
"""
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from sqlalchemy import func

from bot.utils.database import get_db_session
from bot.utils.format_utils import format_remaining_text, format_date
from app.models import Group, Creator, Subscription, Transaction, PricingPlan

logger = logging.getLogger(__name__)

async def setup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Configurar bot no grupo"""
    chat = update.effective_chat
    user = update.effective_user
    
    # Verificar se é um grupo
    if chat.type == 'private':
        text = """
❌ **Comando Exclusivo para Grupos!**

Este comando deve ser usado dentro do seu grupo VIP.

📋 **Como configurar:**
1. Adicione o bot ao seu grupo
2. Promova o bot a administrador com permissões:
   • Adicionar novos membros
   • Remover membros
   • Gerenciar links de convite
3. Use /setup dentro do grupo

💡 **Importante:**
Você precisa estar cadastrado como criador no site primeiro.
Acesse: https://televip.app/register
"""
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        return
    
    # Verificar se o bot é admin
    try:
        bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
        if bot_member.status not in ['administrator', 'creator']:
            text = """
❌ **Bot Precisa Ser Administrador!**

Por favor, promova o bot a administrador com estas permissões:

✅ Adicionar novos membros
✅ Remover membros  
✅ Gerenciar links de convite
✅ Deletar mensagens (opcional)

Após promover, use /setup novamente.
"""
            await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
            return
    except Exception:
        await update.message.reply_text("❌ Erro ao verificar permissões do bot.")
        return
    
    # Verificar se o usuário é admin do grupo
    try:
        user_member = await context.bot.get_chat_member(chat.id, user.id)
        if user_member.status not in ['administrator', 'creator']:
            await update.message.reply_text(
                "❌ Apenas administradores do grupo podem usar este comando!"
            )
            return
    except Exception:
        return

    with get_db_session() as session:
        # Verificar se o usuário é um criador cadastrado
        creator = session.query(Creator).filter_by(
            telegram_id=str(user.id)
        ).first()

        if not creator:
            # Mesmo sem conta vinculada, mostrar o ID do grupo
            text = f"""
📋 **Informacoes do Grupo**

• Nome: {chat.title}
• ID do grupo: `{chat.id}`

Copie o ID acima e cole no formulario de criacao de grupo no site.

⚠️ **Conta Telegram nao vinculada**

Seu Telegram ID: `{user.id}`

Para vincular, acesse seu perfil no site e adicione seu Telegram ID,
ou use /setup novamente apos vincular.
"""
            await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
            return

        # Buscar ou criar grupo
        group = session.query(Group).filter_by(
            telegram_id=str(chat.id)
        ).first()
        
        if group:
            # Grupo já existe - mostrar status
            active_subs = session.query(Subscription).filter_by(
                group_id=group.id,
                status='active'
            ).count()

            # Receita do mês
            start_of_month = datetime.now().replace(day=1, hour=0, minute=0, second=0)
            monthly_revenue = session.query(func.sum(Transaction.net_amount)).filter(
                Transaction.group_id == group.id,
                Transaction.created_at >= start_of_month,
                Transaction.status == 'completed'
            ).scalar() or 0

            # Planos ativos
            active_plans = session.query(PricingPlan).filter_by(
                group_id=group.id,
                is_active=True
            ).count()

            text = f"""
✅ **Grupo Ja Configurado!**

📊 **Status Atual:**
• Nome: {group.name}
• ID: `{chat.id}`
• Assinantes ativos: {active_subs}
• Receita este mes: R$ {monthly_revenue:.2f}
• Planos configurados: {active_plans}

🔗 **Link de Assinatura:**
`https://t.me/{context.bot.username}?start=g_{group.invite_slug}`

📋 **Comandos Disponiveis:**
/stats - Ver estatisticas detalhadas
/broadcast - Enviar mensagem aos assinantes

🔒 **Seguranca Anti-Fraude:**
• O bot gera links de uso unico para cada assinante
• Usuarios sem assinatura sao removidos automaticamente
• Auditoria periodica de membros ativa

⚠️ **IMPORTANTE:** Desative TODOS os links de convite permanentes
do grupo. Use apenas os links gerados pelo bot para cada assinante.
Links permanentes permitem que usuarios removidos voltem ao grupo!

💡 Configure seus planos em:
https://televip.app/dashboard
"""
            
            keyboard = [
                [
                    InlineKeyboardButton("📊 Ver Estatísticas", callback_data="admin_stats"),
                    InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")
                ],
                [
                    InlineKeyboardButton("🌐 Ir para Dashboard", url="https://televip.app/dashboard")
                ]
            ]
            
        else:
            # Criar novo grupo
            group = Group(
                creator_id=creator.id,
                name=chat.title,
                telegram_id=str(chat.id),
                description=f"Grupo VIP de @{creator.username or creator.name}",
                is_active=True
            )
            session.add(group)
            session.commit()
            
            text = f"""
🎉 **Grupo Configurado com Sucesso!**

Seu grupo foi registrado na plataforma TeleVIP.

📋 **Informações:**
• Nome: {chat.title}
• ID: `{chat.id}`
• Criador: @{creator.username or creator.name}

🔗 **Seu Link de Assinatura:**
`https://t.me/{context.bot.username}?start=g_{group.invite_slug}`

📌 **Próximos Passos:**
1. Configure os planos de preço no site
2. Compartilhe o link com seus seguidores
3. O bot gerenciará tudo automaticamente!

⚙️ **Funcionalidades Ativadas:**
✅ Adicionar assinantes pagos automaticamente
✅ Remover quando a assinatura expirar
✅ Enviar lembretes de renovacao
✅ Auditoria periodica de membros
✅ Protecao contra chargeback

🔒 **IMPORTANTE - Seguranca:**
Desative TODOS os links de convite permanentes deste grupo!
O bot gera links de uso unico para cada assinante.
Links permanentes permitem que usuarios removidos voltem ao grupo.

💡 Acesse o dashboard para configurar planos:
https://televip.app/dashboard
"""
            
            keyboard = [
                [
                    InlineKeyboardButton("⚙️ Configurar Planos", url="https://televip.app/dashboard"),
                    InlineKeyboardButton("📊 Ver Stats", callback_data="admin_stats")
                ]
            ]
        
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostrar estatísticas do grupo ou do criador"""
    chat = update.effective_chat
    user = update.effective_user
    
    # Se for no privado, mostrar stats de todos os grupos
    if chat.type == 'private':
        await show_creator_stats(update, context)
        return
    
    # No grupo, verificar permissões
    try:
        user_member = await context.bot.get_chat_member(chat.id, user.id)
        if user_member.status not in ['administrator', 'creator']:
            await update.message.reply_text(
                "❌ Apenas administradores podem ver estatísticas!"
            )
            return
    except Exception:
        return

    # Mostrar stats do grupo
    await show_group_stats(update, context, chat.id)

async def show_group_stats(update: Update, context: ContextTypes.DEFAULT_TYPE, group_telegram_id: str):
    """Mostrar estatísticas detalhadas de um grupo"""
    with get_db_session() as session:
        group = session.query(Group).filter_by(
            telegram_id=str(group_telegram_id)
        ).first()
        
        if not group:
            await update.message.reply_text(
                "❌ Grupo não configurado. Use /setup primeiro."
            )
            return
        
        # Estatísticas gerais
        total_subs = session.query(Subscription).filter_by(
            group_id=group.id
        ).count()
        
        active_subs = session.query(Subscription).filter_by(
            group_id=group.id,
            status='active'
        ).count()
        
        # Receitas
        total_revenue = session.query(func.sum(Transaction.net_amount)).filter(
            Transaction.group_id == group.id,
            Transaction.status == 'completed'
        ).scalar() or 0
        
        # Receita do mês atual
        start_of_month = datetime.now().replace(day=1, hour=0, minute=0, second=0)
        monthly_revenue = session.query(func.sum(Transaction.net_amount)).filter(
            Transaction.group_id == group.id,
            Transaction.created_at >= start_of_month,
            Transaction.status == 'completed'
        ).scalar() or 0
        
        # Receita dos últimos 30 dias
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        last_30_days_revenue = session.query(func.sum(Transaction.net_amount)).filter(
            Transaction.group_id == group.id,
            Transaction.created_at >= thirty_days_ago,
            Transaction.status == 'completed'
        ).scalar() or 0
        
        # Novos assinantes (últimos 7 dias)
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        new_subs_week = session.query(Subscription).filter(
            Subscription.group_id == group.id,
            Subscription.created_at >= seven_days_ago
        ).count()
        
        # Taxa de renovação
        renewed = session.query(Subscription).filter(
            Subscription.group_id == group.id,
            Subscription.renewed_from_id != None
        ).count()
        
        renewal_rate = (renewed / total_subs * 100) if total_subs > 0 else 0
        
        # Plano mais popular
        popular_plan = session.query(
            PricingPlan.name,
            func.count(Subscription.id).label('count')
        ).join(
            Subscription
        ).filter(
            PricingPlan.group_id == group.id
        ).group_by(
            PricingPlan.id
        ).order_by(
            func.count(Subscription.id).desc()
        ).first()
        
        text = f"""
📊 **Estatísticas - {group.name}**

👥 **Assinantes:**
• Total histórico: {total_subs}
• Ativos agora: {active_subs}
• Novos (7 dias): {new_subs_week}
• Taxa renovação: {renewal_rate:.1f}%

💰 **Receitas:**
• Total geral: R$ {total_revenue:.2f}
• Este mês: R$ {monthly_revenue:.2f}
• Últimos 30 dias: R$ {last_30_days_revenue:.2f}
• Média por assinante: R$ {(total_revenue/total_subs if total_subs > 0 else 0):.2f}

📈 **Performance:**
• Crescimento mensal: {((active_subs/total_subs*100) if total_subs > 0 else 0):.1f}%
• Plano mais popular: {popular_plan[0] if popular_plan else 'N/A'}
• Ticket médio: R$ {(monthly_revenue/active_subs if active_subs > 0 else 0):.2f}

🔗 **Link do Grupo:**
`https://t.me/{context.bot.username}?start=g_{group.invite_slug}`

📅 Atualizado: {format_date(datetime.utcnow(), include_time=True)}
"""
        
        keyboard = [
            [
                InlineKeyboardButton("🌐 Dashboard Web", url="https://televip.app/dashboard")
            ]
        ]
        
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def show_creator_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostrar estatísticas gerais do criador"""
    user = update.effective_user
    
    with get_db_session() as session:
        creator = session.query(Creator).filter_by(
            telegram_id=str(user.id)
        ).first()
        
        if not creator:
            text = """
❌ **Você não é um criador cadastrado!**

Para se tornar criador:
1. Acesse https://televip.app/register
2. Complete seu perfil
3. Volte aqui para ver suas estatísticas

💡 Taxa de apenas 1% sobre vendas!
"""
            await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
            return
        
        # Buscar todos os grupos do criador
        groups = session.query(Group).filter_by(
            creator_id=creator.id,
            is_active=True
        ).all()
        
        if not groups:
            text = """
📊 **Suas Estatísticas**

Você ainda não tem grupos configurados.

Para começar:
1. Adicione o bot a um grupo
2. Promova o bot a administrador
3. Use /setup dentro do grupo

💡 Você pode ter múltiplos grupos!
"""
            await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
            return
        
        # Calcular estatísticas totais
        total_subs = 0
        total_active = 0
        total_revenue = 0
        monthly_revenue = 0
        
        start_of_month = datetime.now().replace(day=1, hour=0, minute=0, second=0)
        
        text = f"""
📊 **Dashboard do Criador**

👤 **Perfil:** @{creator.username or creator.name}
📅 **Membro desde:** {format_date(creator.created_at)}

**💼 Seus Grupos ({len(groups)}):**

"""
        
        for group in groups:
            # Stats por grupo
            active = session.query(Subscription).filter_by(
                group_id=group.id,
                status='active'
            ).count()
            
            revenue = session.query(func.sum(Transaction.net_amount)).filter(
                Transaction.group_id == group.id,
                Transaction.status == 'completed'
            ).scalar() or 0
            
            month_revenue = session.query(func.sum(Transaction.net_amount)).filter(
                Transaction.group_id == group.id,
                Transaction.created_at >= start_of_month,
                Transaction.status == 'completed'
            ).scalar() or 0
            
            total_active += active
            total_revenue += revenue
            monthly_revenue += month_revenue
            
            text += f"""
📌 **{group.name}**
• Assinantes: {active}
• Receita total: R$ {revenue:.2f}
• Este mês: R$ {month_revenue:.2f}

"""
        
        # Totais
        text += f"""
━━━━━━━━━━━━━━━━━━━
💰 **Totais:**
• Assinantes ativos: {total_active}
• Receita total: R$ {total_revenue:.2f}
• Receita este mês: R$ {monthly_revenue:.2f}
• Saldo disponível: R$ {creator.available_balance:.2f}

📈 **Métricas:**
• Ticket médio: R$ {(total_revenue/total_active if total_active > 0 else 0):.2f}
• Taxa da plataforma: 1%
• Você recebe: 99% do valor

{f"💵 **Saque disponível!** Você tem R$ {creator.available_balance:.2f} para sacar." if creator.available_balance >= 10 else ""}
"""
        
        keyboard = [
            [
                InlineKeyboardButton("🌐 Dashboard Web", url="https://televip.app/dashboard")
            ]
        ]
        
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enviar mensagem para todos os assinantes"""
    chat = update.effective_chat
    user = update.effective_user
    
    # Verificar se é admin
    if chat.type != 'private':
        try:
            user_member = await context.bot.get_chat_member(chat.id, user.id)
            if user_member.status not in ['administrator', 'creator']:
                await update.message.reply_text(
                    "❌ Apenas administradores podem enviar broadcast!"
                )
                return
        except Exception:
            return

    # Verificar se tem texto
    if not context.args:
        text = """
📢 **Como usar o Broadcast**

Envie sua mensagem após o comando:
`/broadcast Sua mensagem aqui`

**Exemplo:**
`/broadcast 🎉 Novo conteúdo exclusivo disponível! Confira no grupo.`

**💡 Dicas:**
• Use emojis para destacar
• Seja breve e direto
• Evite spam (máx 1 por dia)
• Respeite seus assinantes

**⚠️ Importante:**
A mensagem será enviada para TODOS os assinantes ativos do grupo.
"""
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        return
    
    # Pegar mensagem
    broadcast_text = ' '.join(context.args)
    
    # Se no privado, perguntar qual grupo
    if chat.type == 'private':
        await select_group_for_broadcast(update, context, broadcast_text)
    else:
        # Broadcast para o grupo atual
        await confirm_broadcast(update, context, chat.id, broadcast_text)

async def select_group_for_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str):
    """Selecionar grupo para broadcast quando no privado"""
    user = update.effective_user
    
    with get_db_session() as session:
        creator = session.query(Creator).filter_by(
            telegram_id=str(user.id)
        ).first()
        
        if not creator:
            await update.message.reply_text("❌ Você não é um criador cadastrado!")
            return
        
        groups = session.query(Group).filter_by(
            creator_id=creator.id,
            is_active=True
        ).all()
        
        if not groups:
            await update.message.reply_text("❌ Você não tem grupos configurados!")
            return
        
        # Salvar mensagem no contexto
        context.user_data['broadcast_message'] = message
        
        text = "📢 **Selecione o grupo para broadcast:**\n\n"
        keyboard = []
        
        for group in groups:
            active_subs = session.query(Subscription).filter_by(
                group_id=group.id,
                status='active'
            ).count()
            
            text += f"• {group.name} ({active_subs} assinantes)\n"
            
            keyboard.append([
                InlineKeyboardButton(
                    f"{group.name} ({active_subs})",
                    callback_data=f"broadcast_to_{group.id}"
                )
            ])
        
        keyboard.append([
            InlineKeyboardButton("❌ Cancelar", callback_data="cancel_broadcast")
        ])
        
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def confirm_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE, group_telegram_id: str, message: str):
    """Confirmar envio de broadcast"""
    context.user_data['broadcast_message'] = message
    context.user_data['broadcast_group_telegram_id'] = str(group_telegram_id)

    text = (
        f"📢 **Confirmar Broadcast**\n\n"
        f"**Mensagem:**\n{message}\n\n"
        f"Deseja enviar esta mensagem para todos os assinantes ativos?"
    )
    keyboard = [
        [
            InlineKeyboardButton("✅ Enviar", callback_data=f"broadcast_confirm"),
            InlineKeyboardButton("❌ Cancelar", callback_data="cancel_broadcast")
        ]
    ]
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_broadcast_to_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para callback broadcast_to_GROUPID"""
    query = update.callback_query
    await query.answer()

    group_id = int(query.data.replace("broadcast_to_", ""))
    message = context.user_data.get('broadcast_message', '')

    if not message:
        await query.edit_message_text("❌ Nenhuma mensagem para enviar. Use /broadcast <mensagem>")
        return

    context.user_data['broadcast_group_id'] = group_id

    with get_db_session() as session:
        group = session.query(Group).get(group_id)
        group_name = group.name if group else 'Desconhecido'
        active_count = session.query(Subscription).filter_by(
            group_id=group_id, status='active'
        ).count()

    text = (
        f"📢 **Confirmar Broadcast**\n\n"
        f"**Grupo:** {group_name}\n"
        f"**Assinantes ativos:** {active_count}\n\n"
        f"**Mensagem:**\n{message}\n\n"
        f"Confirma o envio?"
    )
    keyboard = [
        [
            InlineKeyboardButton("✅ Enviar", callback_data="broadcast_confirm"),
            InlineKeyboardButton("❌ Cancelar", callback_data="cancel_broadcast")
        ]
    ]
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_broadcast_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enviar broadcast para todos os assinantes ativos do grupo"""
    query = update.callback_query
    await query.answer("Enviando...")

    message = context.user_data.get('broadcast_message', '')
    group_id = context.user_data.get('broadcast_group_id')
    group_telegram_id = context.user_data.get('broadcast_group_telegram_id')

    if not message:
        await query.edit_message_text("❌ Nenhuma mensagem para enviar.")
        return

    with get_db_session() as session:
        if group_id:
            group = session.query(Group).get(group_id)
        elif group_telegram_id:
            group = session.query(Group).filter_by(telegram_id=str(group_telegram_id)).first()
        else:
            await query.edit_message_text("❌ Grupo nao identificado.")
            return

        if not group:
            await query.edit_message_text("❌ Grupo nao encontrado.")
            return

        # Buscar assinantes ativos
        subs = session.query(Subscription).filter_by(
            group_id=group.id, status='active'
        ).all()

        if not subs:
            await query.edit_message_text("❌ Nenhum assinante ativo neste grupo.")
            return

        sent = 0
        failed = 0
        for sub in subs:
            try:
                await context.bot.send_message(
                    chat_id=int(sub.telegram_user_id),
                    text=f"📢 **Mensagem de {group.name}:**\n\n{message}",
                    parse_mode=ParseMode.MARKDOWN
                )
                sent += 1
            except Exception as e:
                logger.warning(f"Falha ao enviar broadcast para {sub.telegram_user_id}: {e}")
                failed += 1

        # Atualizar last_broadcast_at
        group.last_broadcast_at = datetime.utcnow()
        session.commit()

    # Limpar dados do contexto
    context.user_data.pop('broadcast_message', None)
    context.user_data.pop('broadcast_group_id', None)
    context.user_data.pop('broadcast_group_telegram_id', None)

    await query.edit_message_text(
        f"✅ **Broadcast Enviado!**\n\n"
        f"**Grupo:** {group.name}\n"
        f"**Enviados:** {sent}\n"
        f"**Falhas:** {failed}"
    )


async def handle_cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancelar broadcast"""
    query = update.callback_query
    await query.answer()
    context.user_data.pop('broadcast_message', None)
    context.user_data.pop('broadcast_group_id', None)
    context.user_data.pop('broadcast_group_telegram_id', None)
    await query.edit_message_text("❌ Broadcast cancelado.")

# ==================== FUNÇÕES EXTRAS ADICIONADAS ====================

async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler quando usuário tenta entrar no grupo"""
    chat = update.effective_chat
    user = update.effective_user
    
    # Verificar se é um grupo
    if chat.type not in ['group', 'supergroup']:
        return
    
    with get_db_session() as session:
        # Verificar se o usuário tem assinatura ativa
        group = session.query(Group).filter_by(
            telegram_id=str(chat.id)
        ).first()
        
        if not group:
            return
        
        subscription = session.query(Subscription).filter_by(
            group_id=group.id,
            telegram_user_id=str(user.id),
            status='active'
        ).first()
        
        if not subscription or subscription.end_date < datetime.utcnow():
            # Remover usuário não autorizado
            try:
                await context.bot.ban_chat_member(
                    chat_id=chat.id,
                    user_id=user.id
                )
                await context.bot.unban_chat_member(
                    chat_id=chat.id,
                    user_id=user.id
                )
                logger.warning(f"Usuário {user.id} removido do grupo {chat.id} - sem assinatura")
                
                # Enviar mensagem privada ao usuário
                try:
                    await context.bot.send_message(
                        chat_id=user.id,
                        text=f"""
❌ **Acesso Negado**

Você foi removido do grupo **{group.name}** porque não possui uma assinatura ativa.

Para acessar o grupo, você precisa:
1. Assinar um plano
2. Aguardar a confirmação do pagamento
3. Usar o link de acesso fornecido

🔗 Link para assinar:
https://t.me/{context.bot.username}?start=g_{group.invite_slug}

Se você já pagou, aguarde a confirmação ou entre em contato com o suporte.
""",
                        parse_mode=ParseMode.MARKDOWN
                    )
                except Exception:
                    pass  # Usuário pode ter bloqueado o bot
                    
            except Exception as e:
                logger.error(f"Erro ao remover usuário do grupo: {e}")
        else:
            # Usuário autorizado - enviar mensagem de boas-vindas
            logger.info(f"Usuário {user.id} autorizado no grupo {chat.id}")
            
            # Mensagem de boas-vindas personalizada
            remaining = format_remaining_text(subscription.end_date)

            try:
                welcome_text = f"""
🎉 Bem-vindo(a) ao grupo **{group.name}**, {user.first_name}!

✅ Sua assinatura está ativa
📅 Plano: {subscription.plan.name}
⏳ Tempo restante: {remaining}
📆 Expira em: {format_date(subscription.end_date)}

📌 **Regras do Grupo:**
• Respeite todos os membros
• Não compartilhe conteúdo do grupo
• Proibido spam ou divulgação
• Mantenha o foco no tema do grupo

💡 Aproveite o conteúdo exclusivo!
"""
                
                # Enviar como mensagem privada para não poluir o grupo
                await context.bot.send_message(
                    chat_id=user.id,
                    text=welcome_text,
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception:
                pass  # Não é crítico se falhar

async def handle_new_chat_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para novos membros no chat - verificacao rapida de assinatura"""
    message = update.message

    if not message or not message.new_chat_members:
        return

    chat = message.chat

    for new_member in message.new_chat_members:
        # Ignorar se for o proprio bot
        if new_member.id == context.bot.id:
            continue

        # Ignorar bots (admins podem adicionar bots livremente)
        if new_member.is_bot:
            continue

        with get_db_session() as session:
            group = session.query(Group).filter_by(
                telegram_id=str(chat.id)
            ).first()

            if not group:
                continue

            # Verificar se esta na lista de excecao (whitelist criador ou system)
            if group.is_whitelisted(str(new_member.id)) or group.is_system_whitelisted(str(new_member.id)):
                logger.info(f"Usuario {new_member.id} na whitelist do grupo {chat.id} - permitido")
                continue

            # Verificar se é admin/creator do grupo (moderadores)
            try:
                member_info = await context.bot.get_chat_member(chat.id, new_member.id)
                if member_info.status in ['administrator', 'creator']:
                    logger.info(f"Usuario {new_member.id} e admin do grupo {chat.id} - permitido")
                    continue
            except Exception:
                pass  # Se falhar, continua verificacao normal

            subscription = session.query(Subscription).filter_by(
                group_id=group.id,
                telegram_user_id=str(new_member.id),
                status='active'
            ).first()

            if not subscription or subscription.end_date < datetime.utcnow():
                # UNAUTHORIZED — kick FIRST, then notify (minimize access window)
                try:
                    await context.bot.ban_chat_member(
                        chat_id=chat.id,
                        user_id=new_member.id
                    )
                    await context.bot.unban_chat_member(
                        chat_id=chat.id,
                        user_id=new_member.id,
                        only_if_banned=True
                    )
                    logger.warning(f"Usuario {new_member.id} removido do grupo {chat.id} - sem assinatura")

                    # Delete the "joined" system message to avoid confusion
                    try:
                        await message.delete()
                    except Exception:
                        pass

                    # Notify user AFTER removal (non-blocking)
                    try:
                        await context.bot.send_message(
                            chat_id=new_member.id,
                            text=(
                                f"❌ **Acesso Negado**\n\n"
                                f"Voce foi removido do grupo **{group.name}** "
                                f"porque nao possui uma assinatura ativa.\n\n"
                                f"🔗 Para assinar:\n"
                                f"https://t.me/{context.bot.username}?start=g_{group.invite_slug}"
                            ),
                            parse_mode=ParseMode.MARKDOWN
                        )
                    except Exception:
                        pass  # User may have blocked bot

                except Exception as e:
                    logger.error(f"Erro ao remover usuario nao autorizado: {e}")
            else:
                # Authorized — send welcome privately
                logger.info(f"Usuario {new_member.id} autorizado no grupo {chat.id}")
                remaining = format_remaining_text(subscription.end_date)

                try:
                    await context.bot.send_message(
                        chat_id=new_member.id,
                        text=(
                            f"🎉 Bem-vindo(a) ao grupo **{group.name}**, {new_member.first_name}!\n\n"
                            f"✅ Sua assinatura esta ativa\n"
                            f"📅 Plano: {subscription.plan.name}\n"
                            f"⏳ Tempo restante: {remaining}\n\n"
                            f"💡 Aproveite o conteudo exclusivo!"
                        ),
                        parse_mode=ParseMode.MARKDOWN
                    )
                except Exception:
                    pass