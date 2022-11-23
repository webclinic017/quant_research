class CashDistribute():
    """
    头寸分配，
    """

    def __init__(self, amount, periods):
        """
        :param amount: 总金额
        :param periods: 投资期数（多少周）
        :return:
        """

        periods = periods / 2  # 假设分牛熊市对半，那么，能投的周，肯定是一半
        self.amount_once = amount / periods  # 每次的最大购买金额

    def calculate(self, ma_value, current_value):
        """
        我们的算法里，当前值一直在均值之下，所以就
        :param base_value: 指数的均值
        :param current_value: 指数当前值
        :return:
        """
        ratio = current_value / ma_value
        # 距离均线5%以内，投资30%的配额
        if ratio < 0.05: return self.amount_once * 0.3
        # 距离均线5%~10%以内，投资50%的配额
        if ratio < 0.1: return self.amount_once * 0.5
        # 距离均线10%~30%以内，投资80%的配额
        if ratio < 0.3: return self.amount_once * 0.8
        # 距离均线30%~50%以内，投资100%的配额
        if ratio < 0.5: return self.amount_once * 1
        # 大于50%的跌幅，就投1.5倍的配额
        return self.amount_once * 1.5
