# bot/handlers/start.py
"""
Handler do comando /start com suporte multi-criador
CORREÇÃO: Adicionar verificação de transações pendentes
"""
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from bot.utils.database import get_db_session
from bot.keyboards.menus import get_main_menu, get_plans_menu
from app.models import Group, Creator, PricingPlan, Subscription, Transaction

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
    """Mostrar dashboard com assinaturas do usuário - VERSÃO CORRIGIDA"""
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
        # NOVA VERIFICAÇÃO: Buscar transações pendentes
        if not context.user_data.get('skip_pending_check'):
            pending_transactions = session.query(Transaction).join(
                Subscription
            ).filter(
                Subscription.telegram_user_id == str(user.id),
                Transaction.status == 'pending',
                Transaction.created_at >= datetime.utcnow() - timedelta(hours=2)
            ).all()
            
            if pending_transactions:
                logger.info(f"Encontradas {len(pending_transactions)} transações pendentes para usuário {user.id}")
                
                # Mostrar botão para verificar pagamento
                text = f"""
👋 Olá {user.first_name}!

🔄 **Detectamos um pagamento pendente!**

Parece que você tem um pagamento em processamento. 

💡 Se você acabou de fazer um pagamento, clique no botão abaixo para verificar o status.

Se não fez nenhum pagamento recentemente, pode continuar para o menu principal.
"""
                keyboard = [
                    [
                        InlineKeyboardButton("🔄 Verificar Pagamento", callback_data="check_payment_status")
                    ],
                    [
                        InlineKeyboardButton("🏠 Continuar para Menu", callback_data="continue_to_menu")
                    ]
                ]
                
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
                return
        
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

Precisa de ajuda? Use /help ou clique no botão abaixo.
"""
            keyboard = [
                [
                    InlineKeyboardButton("🔍 Descobrir Grupos", callback_data="discover"),
                    InlineKeyboardButton("❓ Ajuda", callback_data="help")
                ]
            ]
        else:
            # Usuário com assinaturas - mostrar dashboard
            text = f"""
👋 Olá {user.first_name}!

📊 **Suas Assinaturas Ativas:** {len(subscriptions)}

"""
            # Listar assinaturas ativas
            for sub in subscriptions[:5]:  # Mostrar até 5
                days_left = (sub.end_date - datetime.utcnow()).days
                status_emoji = "🟢" if days_left > 7 else "🟡" if days_left > 3 else "🔴"
                
                text += f"{status_emoji} **{sub.group.name}**\n"
                text += f"   Plano: {sub.plan.name}\n"
                text += f"   Expira em: {days_left} dias\n\n"
            
            if len(subscriptions) > 5:
                text += f"... e mais {len(subscriptions) - 5} assinaturas\n\n"
            
            text += "Use /status para ver detalhes completos."
            
            keyboard = [
                [
                    InlineKeyboardButton("📊 Ver Todas", callback_data="check_status"),
                    InlineKeyboardButton("🔍 Descobrir Mais", callback_data="discover")
                ],
                [
                    InlineKeyboardButton("❓ Ajuda", callback_data="help")
                ]
            ]
        
        # Enviar ou editar mensagem
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
    
    try:
        group_id = int(group_id)
    except ValueError:
        await update.message.reply_text("❌ Link inválido.")
        return
    
    with get_db_session() as session:
        # Buscar grupo
        group = session.query(Group).get(group_id)
        if not group or not group.is_active:
            await update.message.reply_text("❌ Grupo não encontrado ou inativo.")
            return
        
        # Verificar se já tem assinatura ativa
        existing_sub = session.query(Subscription).filter_by(
            group_id=group_id,
            telegram_user_id=str(user.id),
            status='active'
        ).first()
        
        if existing_sub:
            days_left = (existing_sub.end_date - datetime.utcnow()).days
            text = f"""
✅ **Você já é assinante!**

**Grupo:** {group.name}
**Plano atual:** {existing_sub.plan.name}
**Dias restantes:** {days_left}

Sua assinatura expira em: {existing_sub.end_date.strftime('%d/%m/%Y')}
"""
            keyboard = [
                [
                    InlineKeyboardButton("📊 Ver Status", callback_data="check_status"),
                    InlineKeyboardButton("🏠 Menu Principal", callback_data="back_to_start")
                ]
            ]
            
            await update.message.reply_text(
                text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        # Buscar planos disponíveis
        plans = session.query(PricingPlan).filter_by(
            group_id=group_id,
            is_active=True
        ).order_by(PricingPlan.price).all()
        
        if not plans:
            await update.message.reply_text("❌ Nenhum plano disponível para este grupo.")
            return
        
        # Mostrar informações do grupo e planos
        creator = group.creator
        text = f"""
🎯 **{group.name}**

👤 **Criador:** {creator.name}
📝 **Descrição:** {group.description}
👥 **Assinantes:** {group.total_subscribers}

💎 **Planos disponíveis:**
"""
        
        keyboard = []
        for plan in plans:
            text += f"\n📌 **{plan.name}** - R$ {plan.price:.2f}"
            text += f"\n   ⏱ {plan.duration_days} dias"
            text += f"\n   {plan.description}\n"
            
            keyboard.append([
                InlineKeyboardButton(
                    f"💳 {plan.name} - R$ {plan.price:.2f}",
                    callback_data=f"plan_{group_id}_{plan.id}"
                )
            ])
        
        keyboard.append([
            InlineKeyboardButton("❌ Cancelar", callback_data="cancel")
        ])
        
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando de ajuda"""
    help_text = """
📋 **Central de Ajuda TeleVIP**

**🔸 Comandos Disponíveis:**

/start - Menu principal e suas assinaturas
/status - Detalhes de todas suas assinaturas
/descobrir - Explorar grupos disponíveis
/help - Esta mensagem de ajuda

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
• Problemas com pagamento: @suporte_televip
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