"""
Handler do comando /start com suporte multi-criador
"""
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from bot.utils.database import get_db_session
from bot.keyboards.menus import get_main_menu, get_plans_menu
from app.models import Group, Creator, PricingPlan, Subscription

logger = logging.getLogger(__name__)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler do comando /start
    - Sem parâmetros: mostra dashboard do usuário
    - Com g_XXXXX: inicia fluxo de assinatura
    - Com success_: retorno de pagamento bem-sucedido
    - Com cancel: retorno de pagamento cancelado
    """
    user = update.effective_user
    args = context.args
    
    # Tratar diferentes tipos de argumentos
    if args:
        if args[0].startswith('success_'):
            from bot.handlers.payment import handle_payment_success
            await handle_payment_success(update, context)
            return
        elif args[0] == 'cancel':
            await handle_payment_cancel(update, context)
            return
        elif args[0].startswith('g_'):
            group_id = args[0][2:]
            await start_subscription_flow(update, context, group_id)
            return
    
    # Sem argumentos - mostrar dashboard
    await show_user_dashboard(update, context)

async def show_user_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostrar dashboard com assinaturas do usuário"""
    # Detectar se veio de comando ou callback
    if update.callback_query:
        user = update.callback_query.from_user
        message = update.callback_query.message
        is_callback = True
    else:
        user = update.effective_user
        message = update.message
        is_callback = False
    
    with get_db_session() as session:
        # Buscar todas as assinaturas do usuário
        subscriptions = session.query(Subscription).filter_by(
            telegram_user_id=str(user.id),
            status='active'
        ).order_by(Subscription.end_date).all()
        
        if not subscriptions:
            # Usuário novo - mostrar mensagem de boas-vindas
            text = f"""
👋 Olá {user.first_name}!

Bem-vindo ao **TeleVIP Bot** 🤖

Sou seu assistente para gerenciar assinaturas de grupos VIP no Telegram.

🎯 **O que você pode fazer:**
• Assinar grupos exclusivos
• Gerenciar suas assinaturas
• Descobrir novos conteúdos
• Renovar com desconto

💡 **Como começar:**
Use /descobrir para explorar grupos disponíveis ou clique em um link de convite de um criador.

Precisa de ajuda? Use /help
"""
            keyboard = [
                [
                    InlineKeyboardButton("🔍 Descobrir Grupos", callback_data="discover"),
                    InlineKeyboardButton("❓ Ajuda", callback_data="help")
                ]
            ]
            
        else:
            # Usuário com assinaturas - mostrar dashboard
            text = f"👋 Olá {user.first_name}!\n\n"
            text += f"📊 **Suas Assinaturas Ativas ({len(subscriptions)}):**\n\n"
            
            total_value = 0
            need_renewal = []
            
            for i, sub in enumerate(subscriptions, 1):
                group = sub.group
                creator = group.creator
                plan = sub.plan
                days_left = (sub.end_date - datetime.utcnow()).days
                
                # Calcular valor total
                total_value += plan.price
                
                # Emoji baseado nos dias restantes
                if days_left > 7:
                    emoji = "🟢"
                elif days_left > 3:
                    emoji = "🟡"
                    need_renewal.append(sub)
                else:
                    emoji = "🔴"
                    need_renewal.append(sub)
                
                text += f"{i}. {emoji} **{group.name}**\n"
                text += f"   👤 Criador: @{creator.username or creator.name}\n"
                text += f"   💰 Plano: {plan.name} (R$ {plan.price:.2f})\n"
                text += f"   📅 Expira em: {days_left} dias\n"
                
                if days_left <= 7:
                    text += f"   ⚠️ **Renovar em breve!**\n"
                
                text += "\n"
            
            # Resumo financeiro
            text += f"💎 **Valor total mensal:** R$ {total_value:.2f}\n"
            
            # Botões de ação
            keyboard = []
            
            if need_renewal:
                keyboard.append([
                    InlineKeyboardButton(
                        f"🔄 Renovar ({len(need_renewal)})",
                        callback_data="check_renewals"
                    ),
                    InlineKeyboardButton("📊 Ver Detalhes", callback_data="check_status")
                ])
            else:
                keyboard.append([
                    InlineKeyboardButton("📊 Ver Detalhes", callback_data="check_status")
                ])
            
            keyboard.append([
                InlineKeyboardButton("🔍 Descobrir Mais", callback_data="discover"),
                InlineKeyboardButton("⚙️ Configurações", callback_data="settings")
            ])
        
        # Enviar ou editar mensagem baseado no contexto
        if is_callback:
            await message.edit_text(
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

async def start_subscription_flow(update: Update, context: ContextTypes.DEFAULT_TYPE, group_id: str):
    """Iniciar fluxo de assinatura para um grupo específico"""
    user = update.effective_user
    
    with get_db_session() as session:
        # Buscar grupo
        group = session.query(Group).filter_by(telegram_id=group_id).first()
        
        if not group:
            await update.message.reply_text(
                "❌ Grupo não encontrado.\n\n"
                "Verifique se o link está correto ou entre em contato com o criador.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        if not group.is_active:
            await update.message.reply_text(
                "🚫 Este grupo não está aceitando novas assinaturas no momento.\n\n"
                "Entre em contato com o criador para mais informações.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Verificar se já tem assinatura ativa
        existing_sub = session.query(Subscription).filter_by(
            group_id=group.id,
            telegram_user_id=str(user.id),
            status='active'
        ).first()
        
        if existing_sub:
            days_left = (existing_sub.end_date - datetime.utcnow()).days
            plan = existing_sub.plan
            
            text = f"""
✅ **Você já possui uma assinatura ativa!**

**Grupo:** {group.name}
**Plano:** {plan.name}
**Valor:** R$ {plan.price:.2f}
**Dias restantes:** {days_left}
**Expira em:** {existing_sub.end_date.strftime('%d/%m/%Y')}

{'⚠️ **Sua assinatura expira em breve!** Considere renovar.' if days_left <= 7 else ''}
"""
            
            keyboard = []
            
            if days_left <= 7:
                keyboard.append([
                    InlineKeyboardButton("🔄 Renovar Agora", callback_data=f"renew_{existing_sub.id}")
                ])
            
            keyboard.extend([
                [InlineKeyboardButton("📊 Ver Todas Assinaturas", callback_data="check_status")],
                [InlineKeyboardButton("🔍 Descobrir Outros Grupos", callback_data="discover")]
            ])
            
            await update.message.reply_text(
                text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        # Buscar planos do grupo
        plans = session.query(PricingPlan).filter_by(
            group_id=group.id,
            is_active=True
        ).order_by(PricingPlan.duration_days).all()
        
        if not plans:
            await update.message.reply_text(
                "❌ Este grupo ainda não tem planos configurados.\n\n"
                "Entre em contato com o criador para mais informações.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Mostrar informações do grupo e planos
        creator = group.creator
        
        # Contar assinantes ativos
        active_subscribers = session.query(Subscription).filter_by(
            group_id=group.id,
            status='active'
        ).count()
        
        text = f"""
🎯 **{group.name}**

👤 **Criador:** @{creator.username or creator.name}
👥 **Assinantes:** {active_subscribers}
📝 **Descrição:** {group.description or 'Grupo VIP com conteúdo exclusivo'}

💎 **Escolha seu plano:**
"""
        
        # Adicionar informações dos planos
        for plan in plans:
            price_per_day = plan.price / plan.duration_days
            
            text += f"\n📅 **{plan.name}**\n"
            text += f"   💵 R$ {plan.price:.2f}"
            
            if plan.duration_days == 30:
                text += " por mês"
            elif plan.duration_days == 90:
                text += " por trimestre"
                monthly_equivalent = plan.price / 3
                text += f"\n   💰 Equivale a R$ {monthly_equivalent:.2f}/mês"
            elif plan.duration_days == 365:
                text += " por ano"
                monthly_equivalent = plan.price / 12
                text += f"\n   💰 Equivale a R$ {monthly_equivalent:.2f}/mês"
            else:
                text += f" por {plan.duration_days} dias"
            
            text += f"\n   📊 R$ {price_per_day:.2f} por dia\n"
        
        text += "\n✅ Pagamento seguro via Stripe\n"
        text += "🔄 Cancele quando quiser\n"
        text += "📱 Acesso imediato após pagamento"
        
        # Criar teclado com os planos
        keyboard = get_plans_menu(plans, group.id)
        
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando de ajuda detalhado"""
    help_text = """
📋 **Central de Ajuda TeleVIP**

**🔸 Comandos para Assinantes:**

/start - Painel principal com suas assinaturas
/status - Status detalhado de todas assinaturas
/planos - Listar seus planos ativos
/descobrir - Explorar novos grupos disponíveis
/help - Mostrar esta mensagem de ajuda

**🔹 Comandos para Criadores:**

/setup - Configurar o bot em seu grupo
/stats - Ver estatísticas detalhadas
/broadcast - Enviar mensagem para assinantes
/saques - Gerenciar saques

**💡 Dicas Úteis:**

• 🔔 Ative as notificações para não perder avisos importantes
• 💰 Renove com antecedência e ganhe descontos
• 🔍 Use /descobrir para encontrar conteúdo novo
• 📱 Salve os links dos grupos para acesso rápido

**❓ Perguntas Frequentes:**

**Como assino um grupo?**
Clique no link fornecido pelo criador ou use /descobrir

**Como cancelo uma assinatura?**
As assinaturas não renovam automaticamente

**Posso mudar de plano?**
Sim, quando sua assinatura atual expirar

**É seguro?**
Sim, usamos Stripe para processar pagamentos

**📞 Suporte:**
• Problemas com pagamento: suporte@televip.com
• Dúvidas sobre conteúdo: contate o criador do grupo

🔒 Seus dados estão seguros e protegidos.
"""
    
    await update.message.reply_text(
        help_text,
        parse_mode=ParseMode.MARKDOWN
    )

async def handle_payment_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para pagamento cancelado"""
    text = """
❌ **Pagamento Cancelado**

Seu pagamento foi cancelado e nenhuma cobrança foi realizada.

Se mudou de ideia, você pode:
• Usar o link original do grupo
• Explorar outros grupos com /descobrir
• Ver suas assinaturas atuais com /start

Precisando de ajuda? Use /help
"""
    
    keyboard = [
        [
            InlineKeyboardButton("🔍 Descobrir Grupos", callback_data="discover"),
            InlineKeyboardButton("❓ Ajuda", callback_data="help")
        ]
    ]
    
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )