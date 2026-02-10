# -*- coding: utf-8 -*-
"""
Funções auxiliares para o bot
"""
from datetime import datetime, timedelta

def get_days_left(end_date):
    """Calcular dias restantes de forma segura"""
    if isinstance(end_date, timedelta):
        return end_date.days
    elif isinstance(end_date, datetime):
        delta = end_date - datetime.utcnow()
        return max(0, delta.days)
    else:
        return 0

def format_date_br(date):
    """Formatar data no padrão brasileiro"""
    if isinstance(date, datetime):
        return date.strftime('%d/%m/%Y')
    return str(date)

def calculate_platform_fee(amount, fixed_fee=0.99, percentage_fee=0.0999):
    """Calcular taxa da plataforma"""
    total_fee = fixed_fee + (amount * percentage_fee)
    creator_amount = amount - total_fee
    return {
        'fixed_fee': fixed_fee,
        'percentage_fee': amount * percentage_fee,
        'total_fee': total_fee,
        'creator_amount': creator_amount
    }
