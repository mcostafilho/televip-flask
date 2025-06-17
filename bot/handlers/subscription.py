"""
Handler para gerenciamento de assinaturas
"""
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from bot.utils.database import get_db_session
from bot.keyboards.menus import get_renewal_keyboard
from app.models import Subscription, Group, Creator, PricingPlan, Transaction

logger = logging.getLogger(__name__)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostrar status detalhado de todas as assinaturas"""
    # Detectar se é comando ou callback
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        user = query.from_user
        message = query.message
    else:
        user = update.effective_user
        message = update.message
    
    with get_db_session() as session:
        # Buscar TODAS as assinaturas do usuário
        all_subs = session.query(Subscription).filter_by(
            telegram_user_id=str(user.id)
        ).order_by(
            Subscription.status.desc(),  # Ativas primeiro
            Subscription.end_date.desc()  # Mais recentes primeiro
        ).all()
        
        if not all_subs:
            text = """
📭 **Nenhuma Assinatura Encontrada**

Você ainda não possui nenhuma assinatura.

💡 **Como começar:**
• Use /descobrir para explorar grupos
• Clique em links de convite dos criadores
• Escolha um plano que combina com você

Precisa de ajuda? Use /help
"""
            keyboard = [
                [
                    InlineKeyboardButton("🔍 Descobrir Grupos", callback_data="discover"),
                    InlineKeyboardButton("❓ Ajuda", callback_data="help")
                ]
            ]
            
            await message.reply_text(
                text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        # Separar por status
        active = [s for s in all_subs if s.status == 'active']
        expired = [s for s in all_subs if s.status == 'expired']
        cancelled = [s for s in all_subs if s.status == 'cancelled']
        
        # Calcular estatísticas
        total_spent = sum(t.amount for s in all_subs for t in s.transactions if t.status == 'completed')
        active_value = sum(s.plan.price for s in active)
        
        text = "📊 **Status Completo das Assinaturas**\n\n"
        
        # Resumo
        text += "📈 **Resumo Geral:**\n"
        text += f"• Total de assinaturas: {len(all_subs)}\n"
        text += f"• Ativas: {len(active)} ✅\n"
        text += f"• Expiradas: {len(expired)} ❌\n"
        if cancelled:
            text += f"• Canceladas: {len(cancelled)} 🚫\n"
        text += f"• Valor mensal atual: R$ {active_value:.2f}\n"
        text += f"• Total investido: R$ {total_spent:.2f}\n"
        text += "\n"
        
        # Listar ativas detalhadamente
        if active:
            text += "✅ **ASSINATURAS ATIVAS:**\n\n"
            
            need_renewal_urgent = []
            need_renewal_soon = []
            
            for i, sub in enumerate(active, 1):
                group = sub.group
                creator = group.creator
                plan = sub.plan
                days_left = (sub.end_date - datetime.utcnow()).days
                
                # Classificar urgência
                if days_left <= 3:
                    emoji = "🔴"
                    need_renewal_urgent.append(sub)
                elif days_left <= 7:
                    emoji = "🟡"
                    need_renewal_soon.append(sub)
                else:
                    emoji = "🟢"
                
                text += f"{i}. {emoji} **{group.name}**\n"
                text += f"   👤 Criador: @{creator.username or creator.name}\n"
                text += f"   💰 Plano: {plan.name} (R$ {plan.price:.2f})\n"
                text += f"   📅 Expira: {sub.end_date.strftime('%d/%m/%Y')}\n"
                text += f"   ⏳ Restam: {days_left} dias\n"
                
                # Avisos especiais
                if sub.auto_renew:
                    text += f"   🔄 Renovação automática ativada\n"
                elif days_left <= 3:
                    text += f"   🚨 **EXPIRA EM BREVE! Renove agora!**\n"
                elif days_left <= 7:
                    text += f"   ⚠️ **Renovar em breve**\n"
                
                # Estatísticas da assinatura
                duration = (datetime.utcnow() - sub.start_date).days
                text += f"   📊 Assinante há {duration} dias\n"
                
                text += "\n"
        
        # Listar expiradas recentes
        if expired:
            recent_expired = expired[:5]  # Últimas 5
            text += "\n❌ **EXPIRADAS RECENTEMENTE:**\n\n"
            
            for sub in recent_expired:
                group = sub.group
                days_ago = (datetime.utcnow() - sub.end_date).days
                
                text += f"• **{group.name}**\n"
                text += f"  Expirou há {days_ago} dias ({sub.end_date.strftime('%d/%m/%Y')})\n"
                text += f"  Durou {(sub.end_date - sub.start_date).days} dias\n\n"
            
            if len(expired) > 5:
                text += f"... e mais {len(expired) - 5} assinaturas antigas\n"
        
        # Criar botões baseados no contexto
        keyboard = []
        
        # Botões de renovação se necessário
        if need_renewal_urgent:
            keyboard.append([
                InlineKeyboardButton(
                    f"🚨 Renovar Urgente ({len(need_renewal_urgent)})",
                    callback_data="renew_urgent"
                )
            ])
        
        if need_renewal_soon:
            keyboard.append([
                InlineKeyboardButton(
                    f"⚠️ Renovar em Breve ({len(need_renewal_soon)})",
                    callback_data="renew_soon"
                )
            ])
        
        # Outros botões
        keyboard.extend([
            [
                InlineKeyboardButton("💰 Histórico Financeiro", callback_data="financial_history"),
                InlineKeyboardButton("📈 Estatísticas", callback_data="subscription_stats")
            ],
            [
                InlineKeyboardButton("🔍 Descobrir Novos", callback_data="discover"),
                InlineKeyboardButton("⚙️ Configurações", callback_data="subscription_settings")
            ]
        ])
        
        # Adicionar botão voltar se veio de callback
        if update.callback_query:
            keyboard.append([
                InlineKeyboardButton("⬅️ Voltar", callback_data="back_to_start")
            ])
        
        # Responder
        if update.callback_query:
            await query.edit_message_text(
                text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await message.reply_text(
                text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

async def planos_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Listar todos os planos ativos do usuário"""
    user = update.effective_user
    
    with get_db_session() as session:
        # Buscar apenas assinaturas ativas
        active_subs = session.query(Subscription).filter_by(
            telegram_user_id=str(user.id),
            status='active'
        ).order_by(Subscription.end_date).all()
        
        if not active_subs:
            text = """
📋 **Seus Planos**

Você não possui planos ativos no momento.

Use /descobrir para explorar grupos disponíveis!
"""
            keyboard = [[
                InlineKeyboardButton("🔍 Descobrir Grupos", callback_data="discover")
            ]]
        else:
            text = f"📋 **Seus {len(active_subs)} Planos Ativos**\n\n"
            
            total_monthly = 0
            
            for i, sub in enumerate(active_subs, 1):
                group = sub.group
                plan = sub.plan
                creator = group.creator
                days_left = (sub.end_date - datetime.utcnow()).days
                
                # Calcular valor mensal equivalente
                monthly_value = plan.price * (30 / plan.duration_days)
                total_monthly += monthly_value
                
                text += f"**{i}. {group.name}**\n"
                text += f"👤 @{creator.username or creator.name}\n"
                text += f"📦 Plano: {plan.name}\n"
                text += f"💰 Valor: R$ {plan.price:.2f} ({plan.duration_days} dias)\n"
                text += f"📊 Equivale a R$ {monthly_value:.2f}/mês\n"
                text += f"⏳ Expira em {days_left} dias\n"
                
                # Benefícios do plano (futuro: adicionar campo no banco)
                text += f"✅ Acesso completo ao grupo\n"
                text += f"✅ Suporte prioritário\n"
                text += f"✅ Conteúdo exclusivo\n"
                
                text += "\n"
            
            text += f"💎 **Total mensal:** R$ {total_monthly:.2f}\n"
            
            keyboard = [
                [
                    InlineKeyboardButton("📊 Ver Detalhes", callback_data="check_status"),
                    InlineKeyboardButton("🔄 Renovar", callback_data="check_renewals")
                ],
                [
                    InlineKeyboardButton("🔍 Adicionar Mais", callback_data="discover")
                ]
            ]
        
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def handle_renewal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processar renovação de assinatura"""
    query = update.callback_query
    await query.answer()
    
    # Identificar tipo de renovação
    if query.data == "check_renewals":
        await show_renewals_list(update, context)
    elif query.data == "renew_urgent":
        await show_urgent_renewals(update, context)
    elif query.data == "renew_soon":
        await show_soon_renewals(update, context)
    elif query.data.startswith("renew_"):
        # Renovar assinatura específica
        sub_id = int(query.data.replace("renew_", ""))
        await process_renewal(update, context, sub_id)

async def show_renewals_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostrar lista de assinaturas para renovar"""
    query = update.callback_query
    user = query.from_user
    
    with get_db_session() as session:
        # Buscar assinaturas que expiram em até 15 dias
        expiring = session.query(Subscription).filter(
            Subscription.telegram_user_id == str(user.id),
            Subscription.status == 'active',
            Subscription.end_date <= datetime.utcnow() + timedelta(days=15)
        ).order_by(Subscription.end_date).all()
        
        if not expiring:
            text = """
🔄 **Renovações**

✅ Todas as suas assinaturas estão em dia!

Nenhuma assinatura precisa ser renovada nos próximos 15 dias.
"""
            keyboard = [[
                InlineKeyboardButton("⬅️ Voltar", callback_data="check_status")
            ]]
        else:
            text = f"🔄 **Renovações Disponíveis ({len(expiring)})**\n\n"
            
            keyboard = []
            total_renewal = 0
            
            for sub in expiring:
                group = sub.group
                plan = sub.plan
                days_left = (sub.end_date - datetime.utcnow()).days
                
                # Emoji de urgência
                if days_left <= 3:
                    emoji = "🔴"
                    urgency = "URGENTE"
                elif days_left <= 7:
                    emoji = "🟡"
                    urgency = "Em breve"
                else:
                    emoji = "🟢"
                    urgency = "Disponível"
                
                text += f"{emoji} **{group.name}**\n"
                text += f"   Status: {urgency}\n"
                text += f"   Expira em: {days_left} dias\n"
                text += f"   Valor renovação: R$ {plan.price:.2f}\n\n"
                
                total_renewal += plan.price
                
                # Botão para renovar
                keyboard.append([
                    InlineKeyboardButton(
                        f"{emoji} Renovar {group.name[:20]}... (R$ {plan.price:.2f})",
                        callback_data=f"renew_{sub.id}"
                    )
                ])
            
            text += f"💰 **Total para renovar tudo:** R$ {total_renewal:.2f}\n"
            text += "\n💡 Dica: Renove com antecedência e ganhe descontos!"
            
            keyboard.extend([
                [
                    InlineKeyboardButton("🔄 Renovar Todas", callback_data="renew_all")
                ],
                [
                    InlineKeyboardButton("⬅️ Voltar", callback_data="check_status")
                ]
            ])
        
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def show_urgent_renewals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostrar apenas renovações urgentes (3 dias ou menos)"""
    query = update.callback_query
    user = query.from_user
    
    with get_db_session() as session:
        urgent = session.query(Subscription).filter(
            Subscription.telegram_user_id == str(user.id),
            Subscription.status == 'active',
            Subscription.end_date <= datetime.utcnow() + timedelta(days=3)
        ).order_by(Subscription.end_date).all()
        
        text = "🚨 **Renovações Urgentes**\n\n"
        text += "Estas assinaturas expiram em 3 dias ou menos!\n\n"
        
        keyboard = []
        
        for sub in urgent:
            group = sub.group
            plan = sub.plan
            hours_left = int((sub.end_date - datetime.utcnow()).total_seconds() / 3600)
            
            if hours_left < 24:
                time_text = f"{hours_left} horas"
            else:
                time_text = f"{hours_left // 24} dias"
            
            text += f"🔴 **{group.name}**\n"
            text += f"   ⏰ Expira em: {time_text}!\n"
            text += f"   💰 Renovar por: R$ {plan.price:.2f}\n\n"
            
            keyboard.append([
                InlineKeyboardButton(
                    f"🚨 Renovar {group.name[:25]}...",
                    callback_data=f"renew_{sub.id}"
                )
            ])
        
        keyboard.append([
            InlineKeyboardButton("⬅️ Voltar", callback_data="check_status")
        ])
        
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def process_renewal(update: Update, context: ContextTypes.DEFAULT_TYPE, sub_id: int):
    """Processar renovação de uma assinatura específica"""
    query = update.callback_query
    
    with get_db_session() as session:
        sub = session.query(Subscription).get(sub_id)
        
        if not sub:
            await query.edit_message_text("❌ Assinatura não encontrada.")
            return
        
        group = sub.group
        plan = sub.plan
        
        # Simular renovação com desconto
        days_left = (sub.end_date - datetime.utcnow()).days
        
        if days_left >= 5:
            discount = 0.1  # 10% de desconto
            discount_text = "10% de desconto por renovação antecipada!"
        else:
            discount = 0
            discount_text = ""
        
        final_price = plan.price * (1 - discount)
        
        text = f"""
🔄 **Renovar Assinatura**

**Grupo:** {group.name}
**Plano atual:** {plan.name}
**Duração:** {plan.duration_days} dias
**Valor original:** R$ {plan.price:.2f}
"""
        
        if discount > 0:
            text += f"\n✨ **{discount_text}**\n"
            text += f"**Valor com desconto:** R$ {final_price:.2f}\n"
            text += f"**Você economiza:** R$ {plan.price - final_price:.2f}\n"
        else:
            text += f"\n**Valor:** R$ {final_price:.2f}\n"
        
        text += f"\n📅 **Nova data de expiração:** {(sub.end_date + timedelta(days=plan.duration_days)).strftime('%d/%m/%Y')}"
        
        text += "\n\n✅ A renovação é processada imediatamente"
        text += "\n🔒 Pagamento seguro via Stripe"
        
        # Armazenar dados para pagamento
        context.user_data['renewal'] = {
            'subscription_id': sub_id,
            'group_id': group.id,
            'plan_id': plan.id,
            'amount': final_price,
            'discount': discount
        }
        
        keyboard = [
            [
                InlineKeyboardButton("💳 Pagar com Cartão", callback_data="pay_renewal_stripe"),
                InlineKeyboardButton("💰 Pagar com PIX", callback_data="pay_renewal_pix")
            ],
            [
                InlineKeyboardButton("❌ Cancelar", callback_data="check_renewals")
            ]
        ]
        
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )