# bot/handlers/start.py
"""
Handler do comando /start com suporte multi-criador
VERSÃO CORRIGIDA - Sem referências a plan.description
"""
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from bot.utils.database import get_db_session
from bot.keyboards.menus import get_main_menu, get_plans_menu
from app.models import Group, Creator, PricingPlan, Subscription, Transaction
from bot.handlers.payment_verification import check_payment_from_start

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
    
    logger.info(f"Start command - User: {user.id}, Args: {args}")
    
    # Tratar diferentes tipos de argumentos
    if args:
        if args[0].startswith('success_') or args[0] == 'payment_success':
            await check_payment_from_start(update, context)
            return
        elif args[0] == 'cancel':
            await handle_payment_cancel(update, context)
            return
        elif args[0].startswith('g_'):
            group_identifier = args[0][2:]
            logger.info(f"Iniciando fluxo de assinatura para grupo: {group_identifier}")
            await start_subscription_flow(update, context, group_identifier)
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
        # Verificar transações pendentes
        if not context.user_data.get('skip_pending_check'):
            pending_transactions = session.query(Transaction).join(
                Subscription
            ).filter(
                Subscription.telegram_user_id == str(user.id),
                Transaction.status == 'pending',
                Transaction.created_at >= datetime.utcnow() - timedelta(hours=2)
            ).order_by(Transaction.created_at.desc()).first()
            
            if pending_transactions:
                # Pegar apenas a transação mais recente
                if isinstance(pending_transactions, list) and len(pending_transactions) > 1:
                    pending_transactions = [pending_transactions[0]]
                    logger.info(f"Encontradas {len(pending_transactions)} transações pendentes para usuário {user.id}")
                # CORRIGIDO: Pegar apenas a mais recente
                if pending_transactions and isinstance(pending_transactions, list):
                    pending_transactions = pending_transactions[:1]
                
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
        ).order_by(Subscription.end_date).order_by(Transaction.created_at.desc()).limit(1).all()
        
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
                
                # Verificar se group existe antes de acessar
                if sub.group:
                    text += f"{status_emoji} **{sub.group.name}**\n"
                    text += f"   Plano: {sub.plan.name if sub.plan else 'N/A'}\n"
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

async def start_subscription_flow(update: Update, context: ContextTypes.DEFAULT_TYPE, group_identifier: str):
    """Iniciar fluxo de assinatura para um grupo específico (por slug ou ID legado)"""
    user = update.effective_user

    with get_db_session() as session:
        # Tentar buscar por invite_slug primeiro, fallback para ID numérico (links antigos)
        group = session.query(Group).filter_by(invite_slug=group_identifier).first()
        if not group:
            try:
                group_id = int(group_identifier)
                group = session.query(Group).filter_by(id=group_id).first()
            except ValueError:
                pass
        
        if not group:
            logger.warning(f"Grupo não encontrado - identificador: {group_identifier}")

            await update.message.reply_text(
                "❌ Grupo não encontrado.\n\n"
                "Possíveis causas:\n"
                "• Link expirado ou inválido\n"
                "• Grupo foi removido\n\n"
                "Use /descobrir para ver grupos disponíveis."
            )
            return

        if not group.is_active:
            logger.warning(f"Grupo inativo: {group.name} (ID: {group.id})")
            await update.message.reply_text(
                "❌ Este grupo está temporariamente indisponível.\n\n"
                "Entre em contato com o criador ou use /descobrir para ver outros grupos."
            )
            return
        
        # Log para debug
        logger.info(f"Grupo encontrado: {group.name} (ID: {group.id}, Ativo: {group.is_active})")
        
        # Verificar se já tem assinatura ativa
        existing_sub = session.query(Subscription).filter_by(
            group_id=group.id,
            telegram_user_id=str(user.id),
            status='active'
        ).first()
        
        if existing_sub:
            days_left = (existing_sub.end_date - datetime.utcnow()).days
            text = f"""
✅ **Você já é assinante!**

**Grupo:** {group.name}
**Plano atual:** {existing_sub.plan.name if existing_sub.plan else 'N/A'}
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
            group_id=group.id,
            is_active=True
        ).order_by(PricingPlan.price).all()
        
        if not plans:
            logger.warning(f"Nenhum plano ativo para o grupo {group.name}")
            await update.message.reply_text(
                "❌ Nenhum plano disponível para este grupo no momento.\n\n"
                "Entre em contato com o administrador do grupo."
            )
            return
        
        # Mostrar informações do grupo e planos
        creator = group.creator
        text = f"""
🎯 **{group.name}**

👤 **Criador:** {creator.name if creator else 'N/A'}
📝 **Descrição:** {group.description or 'Grupo VIP exclusivo'}
👥 **Assinantes:** {group.total_subscribers or 0}

💎 **Planos disponíveis:**
"""
        
        keyboard = []
        for plan in plans:
            text += f"\n📌 **{plan.name}** - R$ {plan.price:.2f}"
            text += f"\n   ⏱ {plan.duration_days} dias\n"
            
            keyboard.append([
                InlineKeyboardButton(
                    f"💳 {plan.name} - R$ {plan.price:.2f}",
                    callback_data=f"plan_{group.id}_{plan.id}"
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
Use /status e clique no botão "Cancelar" da assinatura desejada

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