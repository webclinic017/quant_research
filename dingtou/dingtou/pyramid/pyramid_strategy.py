from dingtou.backtest.strategy import Strategy
from dingtou.backtest.utils import get_value, date2str
import logging
import talib
logger = logging.getLogger(__name__)


class PyramidStrategy(Strategy):
    """
    """

    def __init__(self, broker, policy):
        super().__init__(broker, None)
        self.GRID_HEIGHT = 0.02  # 网格高度为1%
        self.policy = policy

    def set_data(self, df_baseline, funds_dict: dict):
        super().set_data(df_baseline, funds_dict)
        df_daily_fund = list(self.funds_dict.values())[0]
        df_daily_fund['sma242'] = talib.SMA(df_daily_fund.close, timeperiod=242)
        df_daily_fund['diff_percent'] = (df_daily_fund.close - df_daily_fund.sma242) / df_daily_fund.sma242
        self.last_grid_position = 0

    def next(self, today, next_trade_date):
        super().next(today, next_trade_date)

        df_daily_fund = list(self.funds_dict.values())[0]  # TODO: 这里先选择了第一只基金，将来多只的时候，要遍历的

        # 先看日数据：1、止损 2、
        s_daily_fund = get_value(df_daily_fund, today)
        if s_daily_fund is None: return

        # 当前和上次位置的距离（单位是百分比）
        diff = s_daily_fund.diff_percent - self.last_grid_position
        grid_num = abs(round(s_daily_fund.diff_percent / self.GRID_HEIGHT))

        # 如果比之前的网格低，且在均线之下，就买入
        # -diff > self.GRID_HEIGHT：下跌多余1个网格
        if s_daily_fund.diff_percent < 0 and diff < 0 and grid_num>1:
            positions = self.policy.calculate(grid_num)
            # 扣除手续费后，下取整算购买份数
            # 追加投资
            if self.broker.buy(s_daily_fund.code, next_trade_date, position=positions):
                logger.debug(">>[%s]%s距离均线%.1f%%/%d个格,低于上次历史%.1f%%,买入%.1f份",
                             date2str(today),
                             s_daily_fund.code,
                             s_daily_fund.diff_percent * 100,
                             grid_num,
                             self.last_grid_position * 100,
                             positions)
                self.last_grid_position = - grid_num * self.GRID_HEIGHT

        # 在均线之上，且，超过之前的高度(diff>0)，且，至少超过1个网格(grid_num>=1)，就卖
        if s_daily_fund.diff_percent > 0 and diff > 0 and grid_num>1:
            positions = self.policy.calculate(grid_num)
            # 扣除手续费后，下取整算购买份数
            if self.broker.sell(s_daily_fund.code, next_trade_date, position=positions):
                logger.debug(">>[%s]%s距离均线%.1f%%/%d个格,高于上次历史%.1f%%,卖出%.1f份",
                             date2str(today),
                             s_daily_fund.code,
                             s_daily_fund.diff_percent * 100,
                             grid_num,
                             self.last_grid_position * 100,
                             positions)
                self.last_grid_position = grid_num * self.GRID_HEIGHT

