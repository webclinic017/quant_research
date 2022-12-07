import logging

logger = logging.getLogger(__name__)


class PyramidPolicy():
    def __init__(self):
        # 一网格买入1万份，按照中证500ETF，大约是2~3万人民币
        self.position_per_grid = 10000

    def calculate(self, grid_num):
        """
        距离均线的格子数N，2的N次方份钱
        :param diff_percent:
        :return:
        """
        return self.position_per_grid * grid_num
