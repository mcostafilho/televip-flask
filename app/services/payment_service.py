# Lógica de processamento de pagamentos
# app/services/payment_service.py
"""
Serviço para cálculo de taxas e processamento de pagamentos
"""

class PaymentService:
    """Serviço para cálculo de taxas e processamento de pagamentos"""
    
    # Taxas do sistema
    FIXED_FEE = 0.99  # Taxa fixa por transação
    PERCENTAGE_FEE = 0.08  # 8% de taxa percentual
    
    @staticmethod
    def calculate_fees(gross_amount):
        """
        Calcula as taxas sobre um valor bruto
        Taxa: R$ 0,99 + 8% do valor
        
        Args:
            gross_amount (float): Valor bruto da transação
            
        Returns:
            dict: Dicionário com os valores calculados
        """
        fixed_fee = PaymentService.FIXED_FEE
        percentage_fee = gross_amount * PaymentService.PERCENTAGE_FEE
        total_fee = fixed_fee + percentage_fee
        net_amount = gross_amount - total_fee
        
        return {
            'gross_amount': gross_amount,
            'fixed_fee': fixed_fee,
            'percentage_fee': percentage_fee,
            'total_fee': total_fee,
            'net_amount': net_amount,
            'fee_percentage': (total_fee / gross_amount * 100) if gross_amount > 0 else 0
        }
    
    @staticmethod
    def format_fee_breakdown(gross_amount):
        """
        Formata a quebra de taxas para exibição
        
        Args:
            gross_amount (float): Valor bruto da transação
            
        Returns:
            dict: Dicionário com valores formatados
        """
        fees = PaymentService.calculate_fees(gross_amount)
        
        return {
            'gross': f"R$ {fees['gross_amount']:.2f}",
            'fixed_fee': f"R$ {fees['fixed_fee']:.2f}",
            'percentage_fee': f"R$ {fees['percentage_fee']:.2f} (8%)",
            'total_fee': f"R$ {fees['total_fee']:.2f}",
            'net': f"R$ {fees['net_amount']:.2f}",
            'effective_rate': f"{fees['fee_percentage']:.1f}%"
        }
    
    @staticmethod
    def get_fee_description():
        """Retorna a descrição das taxas"""
        return "R$ 0,99 + 8% por venda"