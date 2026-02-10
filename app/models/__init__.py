# app/models/__init__.py
# Importar modelos na ordem correta para evitar dependências circulares

from .user import Creator
from .group import Group, PricingPlan
from .subscription import Subscription, Transaction
from .report import Report

# Tentar importar Withdrawal se existir
try:
    from .withdrawal import Withdrawal
except ImportError:
    # Se não existir, criar classe dummy
    class Withdrawal:
        pass

# Exportar todos os modelos
__all__ = ['Creator', 'Group', 'PricingPlan', 'Subscription', 'Transaction', 'Withdrawal', 'Report']