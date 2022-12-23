import logging

logger = logging.getLogger(__name__)


class PositionCalculator():
    """
    关于仓位的计算：
    你买入的时候，按照金字塔买入，越跌买的越多，那么问题来了，你买多少钱？或者买多少手？
    我们现在是按照份来，就是固定的手数（场内ETF必须是整手）
    """

    def __init__(self,grid_share):
        self.share_per_grid = grid_share

    def calculate(self, current_grid_position, buy_or_sell):
        """
        根据所在的网格位置，来决定买入多少仓位，卖出多少仓位，最终都是仓位
        :param current_grid_position:当前的网格位置，可以是负的
        :return:
        """

        if buy_or_sell == 'buy':
            return self.share_per_grid * abs(current_grid_position) * 2
        else:  # 'sell'
            return self.share_per_grid * current_grid_position
