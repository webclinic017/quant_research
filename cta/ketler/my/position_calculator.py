import logging
import math

logger = logging.getLogger(__name__)


class PositionCalculator():
    """
    关于仓位的计算：
    你买入的时候，按照金字塔买入，越跌买的越多，那么问题来了，你买多少钱？或者买多少手？
    我们现在是按照份来，就是固定的手数（场内股票必须是整手）
    """

    def __init__(self,grid_share_or_amount, share_or_amount='amount'):
        self.grid_share_or_amount = grid_share_or_amount
        self.share_or_amount = share_or_amount # 按金额，还是，按份数来
        logger.info("初始化份数计算器：按照[%s]来计算每网格，每网格%.0f（股/元）",
                    share_or_amount,
                    grid_share_or_amount)

    def calculate(self, price, current_grid_position, buy_or_sell):
        """
        根据所在的网格位置，来决定买入多少仓位，卖出多少仓位，最终都是仓位
        :param current_grid_position:当前的网格位置，可以是负的
        :return:
        """

        grid_position = self.share_or_amount
        if self.share_or_amount == 'amount':
            # 按照一个保守价格来买入
            grid_position = math.ceil(self.grid_share_or_amount/price)
            # 要是100的整数倍
            grid_position = (grid_position // 100) * 100

        if buy_or_sell == 'buy':
            return grid_position * abs(current_grid_position)
        else:  # 'sell'
            return grid_position * current_grid_position
