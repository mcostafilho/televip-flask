"""
Teclados inline para o bot TeleVIP
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def get_main_menu() -> InlineKeyboardMarkup:
    """Menu principal do bot"""
    keyboard = [
        [
            InlineKeyboardButton("📊 Minhas Assinaturas", callback_data="check_status"),
            InlineKeyboardButton("🔍 Descobrir", callback_data="discover")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_plans_menu(plans: list, group_id: int) -> InlineKeyboardMarkup:
    """Menu de seleção de planos com destaque para economia"""
    keyboard = []
    
    # Ordenar planos por duração
    sorted_plans = sorted(plans, key=lambda p: p.duration_days)
    
    for i, plan in enumerate(sorted_plans):
        # Calcular economia em planos maiores
        if plan.duration_days == 30:
            emoji = "📅"
            label = "Mensal"
            extra = ""
        elif plan.duration_days == 90:
            emoji = "💎"
            label = "Trimestral"
            # Calcular economia vs mensal
            monthly_plan = next((p for p in plans if p.duration_days == 30), None)
            if monthly_plan:
                savings = (monthly_plan.price * 3) - plan.price
                if savings > 0:
                    extra = f" (Economia R$ {savings:.2f})"
                else:
                    extra = ""
            else:
                extra = " (Mais popular)"
        elif plan.duration_days == 365:
            emoji = "👑"
            label = "Anual"
            # Calcular economia vs mensal
            monthly_plan = next((p for p in plans if p.duration_days == 30), None)
            if monthly_plan:
                savings = (monthly_plan.price * 12) - plan.price
                if savings > 0:
                    extra = f" (Economia R$ {savings:.2f})"
                else:
                    extra = ""
            else:
                extra = " (Melhor valor)"
        else:
            emoji = "📆"
            label = f"{plan.duration_days} dias"
            extra = ""
        
        button_text = f"{emoji} {plan.name} - R$ {plan.price:.2f}{extra}"
        
        keyboard.append([
            InlineKeyboardButton(
                button_text,
                callback_data=f"plan_{group_id}_{plan.id}"
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton("❌ Cancelar", callback_data="cancel")
    ])
    
    return InlineKeyboardMarkup(keyboard)

def get_payment_keyboard(checkout_data: dict = None) -> InlineKeyboardMarkup:
    """Teclado para opções de pagamento"""
    keyboard = [
        [
            InlineKeyboardButton("💳 Pagar com Stripe", callback_data="pay_stripe")
        ],
        [
            InlineKeyboardButton("❌ Cancelar", callback_data="cancel_payment")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_cancel_keyboard() -> InlineKeyboardMarkup:
    """Teclado simples com opção de cancelar"""
    keyboard = [[
        InlineKeyboardButton("❌ Cancelar", callback_data="cancel")
    ]]
    return InlineKeyboardMarkup(keyboard)

def get_renewal_keyboard(subscription_id: int) -> InlineKeyboardMarkup:
    """Teclado para renovação de assinatura"""
    keyboard = [[
        InlineKeyboardButton(
            "🔄 Renovar Agora",
            callback_data=f"renew_{subscription_id}"
        ),
        InlineKeyboardButton(
            "⏰ Lembrar Depois",
            callback_data="remind_later"
        )
    ]]
    return InlineKeyboardMarkup(keyboard)

def get_broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    """Teclado de confirmação para broadcast"""
    keyboard = [[
        InlineKeyboardButton("✅ Enviar", callback_data="broadcast_confirm"),
        InlineKeyboardButton("❌ Cancelar", callback_data="broadcast_cancel")
    ]]
    return InlineKeyboardMarkup(keyboard)

