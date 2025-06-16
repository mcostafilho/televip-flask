# app/services/payment_service.py
"""
Serviço para cálculo de taxas e processamento de pagamentos
Taxa: R$ 0,99 + 7,99% por transação
"""

class PaymentService:
    """Serviço para cálculo de taxas e processamento de pagamentos"""
    
    # Taxas do sistema
    FIXED_FEE = 0.99  # Taxa fixa por transação
    PERCENTAGE_FEE = 0.0799  # 7,99% de taxa percentual
    
    @staticmethod
    def calculate_fees(gross_amount):
        """
        Calcula as taxas sobre um valor bruto
        Taxa: R$ 0,99 + 7,99% do valor
        
        Args:
            gross_amount (float): Valor bruto da transação
            
        Returns:
            dict: Dicionário com os valores calculados
        """
        if gross_amount <= 0:
            return {
                'gross_amount': 0,
                'fixed_fee': 0,
                'percentage_fee': 0,
                'total_fee': 0,
                'net_amount': 0,
                'fee_percentage': 0
            }
        
        fixed_fee = PaymentService.FIXED_FEE
        percentage_fee = round(gross_amount * PaymentService.PERCENTAGE_FEE, 2)
        total_fee = round(fixed_fee + percentage_fee, 2)
        net_amount = round(gross_amount - total_fee, 2)
        
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
            'percentage_fee': f"R$ {fees['percentage_fee']:.2f} (7,99%)",
            'total_fee': f"R$ {fees['total_fee']:.2f}",
            'net': f"R$ {fees['net_amount']:.2f}",
            'effective_rate': f"{fees['fee_percentage']:.2f}%"
        }
    
    @staticmethod
    def get_fee_description():
        """Retorna a descrição das taxas"""
        return "R$ 0,99 + 7,99% por transação"
    
    @staticmethod
    def calculate_creator_earnings(transactions):
        """
        Calcula os ganhos do criador baseado nas transações
        
        Args:
            transactions: Lista de transações
            
        Returns:
            dict: Resumo dos ganhos
        """
        total_gross = 0
        total_fees = 0
        total_net = 0
        
        for transaction in transactions:
            if transaction.status == 'completed':
                total_gross += transaction.amount
                total_fees += transaction.total_fee if hasattr(transaction, 'total_fee') else transaction.fee
                total_net += transaction.net_amount
        
        return {
            'total_gross': total_gross,
            'total_fees': total_fees,
            'total_net': total_net,
            'transaction_count': len([t for t in transactions if t.status == 'completed'])
        }
    
    @staticmethod
    def calculate_monthly_projection(current_earnings, days_elapsed):
        """
        Projeta ganhos mensais baseado no histórico
        
        Args:
            current_earnings (float): Ganhos atuais no período
            days_elapsed (int): Dias decorridos
            
        Returns:
            float: Projeção mensal
        """
        if days_elapsed == 0:
            return 0
        
        daily_average = current_earnings / days_elapsed
        return daily_average * 30