import logging

logger = logging.getLogger(__name__)


class GridCashDistribute():
    """
    头寸分配策略
    """

    def __init__(self, amount, periods):
        """
        :param amount: 总金额
        :param periods: 投资期数（多少周）
        :return:
        """
        self.amount_once = amount / periods  # 每次的最大购买金额
        logger.info("预估会投资%d次，每次投资%.2f，总金额是%.2f", periods, self.amount_once, amount)

    def calculate(self, ma_value, current_value):
        pass


class MACashDistribute(CashDistribute):
    def calculate(self, ma_value, current_value):
        """
        ratio = 指数当前值 / 指数均值，
        我们的算法里，当前值一直在均值之下，
        :param base_value: 指数的均值
        :param current_value: 指数当前值
        :return:
        """
        ratio = 1 - current_value / ma_value
        # print(ratio, self.amount_once)
        # 距离均线5%以内，投资50%的配额
        if ratio < 0.05: return self.amount_once * 0.5, 0.5
        # 距离均线5%~10%以内，投资100%的配额
        if ratio < 0.1: return self.amount_once * 1, 1
        # 距离均线10%~30%以内，投资150%的配额
        if ratio < 0.3: return self.amount_once * 1.5, 1.5
        # 大于30%的跌幅，就投1.5倍的配额
        return self.amount_once * 2, 2


class AverageCashDistribute(CashDistribute):
    """完全平均"""

    def calculate(self, ma_value, current_value):
        return self.amount_once
