import logging

logger = logging.getLogger(__name__)


class PositionCalculator():
    """
    关于仓位的计算：
    你买入的时候，按照金字塔买入，越跌买的越多，那么问题来了，你买多少钱？或者买多少手？
    我们现在是按照份来，就是固定的手数（场内ETF必须是整手）
    """

    def __init__(self, overlap_grid_num,grid_share):
        # TODO: 等着后续重构，份数要动态决定
        # self.share_per_grid_dict = share_per_grid_dict
        self.share_per_grid = grid_share
        self.overlap_grid_num = overlap_grid_num

    def calculate(self, current_grid_position, buy_or_sell):
        """
        根据所在的网格位置，来决定买入多少仓位，卖出多少仓位，最终都是仓位
        :param current_grid_position:当前的网格位置，可以是负的
        :return:
        """

        if buy_or_sell == 'buy':
            return self.share_per_grid * abs(current_grid_position)
        else:  # 'sell'
            # 因为有对敲区，所以在卖的数量上，要累加一个overlap_grid_num
            # 计算出卖的时候的倒金字塔的序号，从1开始

            sell_grid_no = current_grid_position + self.overlap_grid_num + 1
            assert sell_grid_no >= 1, f"计算卖的网格位置{sell_grid_no}不对，必须要>=1"

            # logger.debug("current:%d,overlap:%d,sell_grid_no:%d,sell share:%d", current_grid_position, self.overlap_grid_num,sell_grid_no,self.share_per_grid * sell_grid_no)
            return self.share_per_grid * sell_grid_no
