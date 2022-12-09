import logging

logger = logging.getLogger(__name__)


class PyramidPolicy():
    def __init__(self,grid_share_dict):
        # 一网格投入的资金，只是是份数，现在多只基金同时买，改为钱数
        self.grid_share_dict = grid_share_dict

    def calculate(self, fund_code, grid_num):
        """
        距离均线的格子数N，2的N次方份钱
        :param diff_percent:
        :return:
        """
        return self.grid_share_dict[fund_code] * grid_num
