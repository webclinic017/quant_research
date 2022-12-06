import logging

logger = logging.getLogger(__name__)


class PyramidPolicy():
    def __init__(self):
        self.position_per_grid = 20000

    def calculate(self, grid_num):
        """
        距离均线的格子数N，2的N次方份钱
        :param diff_percent:
        :return:
        """
        return self.position_per_grid * grid_num
