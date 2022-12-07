import logging

logger = logging.getLogger(__name__)


class PyramidPolicy():
    def __init__(self,grid_share):
        # 一网格买入1万份，按照中证500ETF，大约是2~3万人民币
        self.grid_share = grid_share

    def calculate(self, grid_num):
        """
        距离均线的格子数N，2的N次方份钱
        :param diff_percent:
        :return:
        """
        return self.grid_share * grid_num
