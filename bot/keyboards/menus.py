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
        ],
        [
            InlineKeyboardButton("💰 Histórico", callback_data="payment_history"),
            InlineKeyboardButton("⚙️ Configurações", callback_data="settings")
        ],
        [
            InlineKeyboardButton("❓ Ajuda", callback_data="help")
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
            InlineKeyboardButton("💳 Cartão de Crédito", callback_data="pay_stripe")
        ],
        [
            InlineKeyboardButton("💰 PIX (Em breve)", callback_data="pay_pix")
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

def get_admin_menu() -> InlineKeyboardMarkup:
    """Menu administrativo para criadores"""
    keyboard = [
        [
            InlineKeyboardButton("📊 Estatísticas", callback_data="admin_stats"),
            InlineKeyboardButton("👥 Assinantes", callback_data="admin_subscribers")
        ],
        [
            InlineKeyboardButton("💰 Financeiro", callback_data="admin_finance"),
            InlineKeyboardButton("⚙️ Configurações", callback_data="admin_settings")
        ],
        [
            InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast"),
            InlineKeyboardButton("🌐 Dashboard Web", url="https://televip.com/dashboard")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    """Teclado de confirmação para broadcast"""
    keyboard = [[
        InlineKeyboardButton("✅ Enviar", callback_data="broadcast_confirm"),
        InlineKeyboardButton("❌ Cancelar", callback_data="broadcast_cancel")
    ]]
    return InlineKeyboardMarkup(keyboard)

def get_settings_menu() -> InlineKeyboardMarkup:
    """Menu de configurações do usuário"""
    keyboard = [
        [
            InlineKeyboardButton("🔔 Notificações", callback_data="settings_notifications"),
            InlineKeyboardButton("💳 Pagamentos", callback_data="settings_payments")
        ],
        [
            InlineKeyboardButton("🔐 Privacidade", callback_data="settings_privacy"),
            InlineKeyboardButton("🌍 Idioma", callback_data="settings_language")
        ],
        [
            InlineKeyboardButton("⬅️ Voltar", callback_data="back_to_start")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_group_settings_menu() -> InlineKeyboardMarkup:
    """Menu de configurações do grupo (admin)"""
    keyboard = [
        [
            InlineKeyboardButton("💰 Gerenciar Planos", callback_data="settings_plans"),
            InlineKeyboardButton("📝 Editar Descrição", callback_data="settings_description")
        ],
        [
            InlineKeyboardButton("🔗 Gerar Novo Link", callback_data="settings_link"),
            InlineKeyboardButton("🚫 Pausar Grupo", callback_data="settings_pause")
        ],
        [
            InlineKeyboardButton("👥 Gerenciar Admins", callback_data="settings_admins"),
            InlineKeyboardButton("📊 Relatórios", callback_data="settings_reports")
        ],
        [
            InlineKeyboardButton("⬅️ Voltar", callback_data="admin_menu")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_subscription_actions_keyboard(subscription_id: int, can_renew: bool = True) -> InlineKeyboardMarkup:
    """Ações disponíveis para uma assinatura"""
    keyboard = []
    
    if can_renew:
        keyboard.append([
            InlineKeyboardButton("🔄 Renovar", callback_data=f"renew_{subscription_id}"),
            InlineKeyboardButton("🎁 Presentear", callback_data=f"gift_{subscription_id}")
        ])
    
    keyboard.extend([
        [
            InlineKeyboardButton("📊 Ver Histórico", callback_data=f"history_{subscription_id}"),
            InlineKeyboardButton("🔔 Configurar Alertas", callback_data=f"alerts_{subscription_id}")
        ],
        [
            InlineKeyboardButton("⬅️ Voltar", callback_data="check_status")
        ]
    ])
    
    return InlineKeyboardMarkup(keyboard)

def get_discovery_filters_keyboard() -> InlineKeyboardMarkup:
    """Filtros para descoberta de grupos"""
    keyboard = [
        [
            InlineKeyboardButton("🏷️ Categorias", callback_data="filter_categories"),
            InlineKeyboardButton("💰 Faixa de Preço", callback_data="filter_price")
        ],
        [
            InlineKeyboardButton("⭐ Avaliação", callback_data="filter_rating"),
            InlineKeyboardButton("📅 Novos", callback_data="filter_new")
        ],
        [
            InlineKeyboardButton("🔄 Limpar Filtros", callback_data="clear_filters"),
            InlineKeyboardButton("⬅️ Voltar", callback_data="discover")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_button(callback_data: str = "back") -> InlineKeyboardMarkup:
    """Botão simples de voltar"""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("⬅️ Voltar", callback_data=callback_data)
    ]])

def get_yes_no_keyboard(yes_callback: str, no_callback: str) -> InlineKeyboardMarkup:
    """Teclado simples Sim/Não"""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Sim", callback_data=yes_callback),
        InlineKeyboardButton("❌ Não", callback_data=no_callback)
    ]])

def get_pagination_keyboard(current_page: int, total_pages: int, base_callback: str) -> list:
    """Criar botões de paginação para listas grandes"""
    buttons = []
    
    # Botão anterior
    if current_page > 1:
        buttons.append(
            InlineKeyboardButton("⬅️", callback_data=f"{base_callback}_page_{current_page-1}")
        )
    
    # Números de página (máximo 5)
    start_page = max(1, current_page - 2)
    end_page = min(total_pages + 1, start_page + 5)
    
    for page in range(start_page, end_page):
        if page == current_page:
            buttons.append(
                InlineKeyboardButton(f"•{page}•", callback_data="current_page")
            )
        else:
            buttons.append(
                InlineKeyboardButton(str(page), callback_data=f"{base_callback}_page_{page}")
            )
    
    # Botão próximo
    if current_page < total_pages:
        buttons.append(
            InlineKeyboardButton("➡️", callback_data=f"{base_callback}_page_{current_page+1}")
        )
    
    return buttons

def get_withdrawal_keyboard(available_balance: float) -> InlineKeyboardMarkup:
    """Teclado para solicitação de saque"""
    if available_balance < 10.0:
        keyboard = [[
            InlineKeyboardButton(
                f"💰 Saldo insuficiente (Mín: R$ 10,00)",
                callback_data="insufficient_balance"
            )
        ]]
    else:
        keyboard = [
            [
                InlineKeyboardButton(
                    f"💵 Sacar R$ {available_balance:.2f}",
                    callback_data="withdraw_all"
                )
            ],
            [
                InlineKeyboardButton("💰 Valor Personalizado", callback_data="withdraw_custom"),
                InlineKeyboardButton("📊 Ver Histórico", callback_data="withdrawal_history")
            ]
        ]
    
    keyboard.append([
        InlineKeyboardButton("⬅️ Voltar", callback_data="creator_dashboard")
    ])
    
    return InlineKeyboardMarkup(keyboard)

def get_support_keyboard() -> InlineKeyboardMarkup:
    """Teclado de opções de suporte"""
    keyboard = [
        [
            InlineKeyboardButton("💬 Chat Suporte", url="https://t.me/televip_suporte"),
            InlineKeyboardButton("📧 Email", callback_data="support_email")
        ],
        [
            InlineKeyboardButton("📚 FAQ", callback_data="support_faq"),
            InlineKeyboardButton("🐛 Reportar Bug", callback_data="support_bug")
        ],
        [
            InlineKeyboardButton("⬅️ Voltar", callback_data="help")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)