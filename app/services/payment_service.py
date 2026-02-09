# app/services/payment_service.py
"""
Serviço para cálculo de taxas e processamento de pagamentos
Taxa: R$ 0,99 + 7,99% por transação
"""
from decimal import Decimal, ROUND_HALF_UP

TWO_PLACES = Decimal('0.01')


class PaymentService:
    """Serviço para cálculo de taxas e processamento de pagamentos"""

    # Taxas do sistema
    FIXED_FEE = Decimal('0.99')  # Taxa fixa por transação
    PERCENTAGE_FEE = Decimal('0.0799')  # 7,99% de taxa percentual

    @staticmethod
    def calculate_fees(gross_amount):
        """
        Calcula as taxas sobre um valor bruto
        Taxa: R$ 0,99 + 7,99% do valor

        Args:
            gross_amount: Valor bruto da transação (float ou Decimal)

        Returns:
            dict: Dicionário com os valores calculados (Decimal)
        """
        gross_amount = Decimal(str(gross_amount))

        if gross_amount <= 0:
            zero = Decimal('0')
            return {
                'gross_amount': zero,
                'fixed_fee': zero,
                'percentage_fee': zero,
                'total_fee': zero,
                'net_amount': zero,
                'fee_percentage': zero
            }

        fixed_fee = PaymentService.FIXED_FEE
        percentage_fee = (gross_amount * PaymentService.PERCENTAGE_FEE).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        total_fee = (fixed_fee + percentage_fee).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        net_amount = (gross_amount - total_fee).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        fee_percentage = (total_fee / gross_amount * 100).quantize(TWO_PLACES, rounding=ROUND_HALF_UP) if gross_amount > 0 else Decimal('0')

        return {
            'gross_amount': gross_amount,
            'fixed_fee': fixed_fee,
            'percentage_fee': percentage_fee,
            'total_fee': total_fee,
            'net_amount': net_amount,
            'fee_percentage': fee_percentage
        }

    @staticmethod
    def format_fee_breakdown(gross_amount):
        """
        Formata a quebra de taxas para exibição

        Args:
            gross_amount: Valor bruto da transação

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
        total_gross = Decimal('0')
        total_fees = Decimal('0')
        total_net = Decimal('0')

        for transaction in transactions:
            if transaction.status == 'completed':
                total_gross += Decimal(str(transaction.amount))
                fee = transaction.total_fee if hasattr(transaction, 'total_fee') and transaction.total_fee else transaction.fee
                total_fees += Decimal(str(fee))
                total_net += Decimal(str(transaction.net_amount))

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
            current_earnings: Ganhos atuais no período
            days_elapsed (int): Dias decorridos

        Returns:
            Decimal: Projeção mensal
        """
        if days_elapsed == 0:
            return Decimal('0')

        current_earnings = Decimal(str(current_earnings))
        daily_average = current_earnings / days_elapsed
        return (daily_average * 30).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
