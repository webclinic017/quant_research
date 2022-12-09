from dingtou.backtest.strategy import Strategy
from dingtou.backtest.utils import get_value, date2str
import logging
import talib
import pandas as pd

logger = logging.getLogger(__name__)


class PyramidStrategy(Strategy):
    """
    """

    def __init__(self, broker, policy, grid_height_dict):
        super().__init__(broker, None)
        self.grid_height_dict = grid_height_dict  # 网格高度为1%
        self.policy = policy
        self.last_grid_position_dict = {}

    def set_data(self, df_baseline, funds_dict: dict):
        super().set_data(df_baseline, funds_dict)
        df_daily_fund = list(self.funds_dict.values())[0]
        df_daily_fund['sma242'] = talib.SMA(df_daily_fund.close, timeperiod=242)
        df_daily_fund['diff_percent'] = (df_daily_fund.close - df_daily_fund.sma242) / df_daily_fund.sma242
        for fund_code in funds_dict.keys():
            self.last_grid_position_dict[fund_code] = 0

    def next(self, today, next_trade_date):
        super().next(today, next_trade_date)

        # 遍历每一只基金，分别处理
        for fund_code, df_fund in self.funds_dict.items():
            self.handle_one_fund(df_fund, today, next_trade_date)

    def handle_one_fund(self, df_daily_fund, today, next_trade_date):
        """
        处理一只基金
        :param df_daily_fund:
        :param today:
        :param next_trade_date:
        :return:
        """

        # 先看日数据：1、止损 2、
        s_daily_fund = get_value(df_daily_fund, today)
        if s_daily_fund is None: return
        if pd.isna(s_daily_fund.diff_percent): return

        # 当前和上次位置的距离（单位是百分比）
        diff = s_daily_fund.diff_percent - self.last_grid_position_dict[s_daily_fund.code]
        grid_num = abs(round(s_daily_fund.diff_percent / self.grid_height_dict[s_daily_fund.code]))

        # 如果比之前的网格低，且在均线之下，就买入
        # -diff > self.grid_height_dict：下跌多余1个网格
        if s_daily_fund.diff_percent < 0 and diff < 0 and grid_num > 1:
            positions = self.policy.calculate(s_daily_fund.code, grid_num)
            # 扣除手续费后，下取整算购买份数
            # 追加投资
            if self.broker.buy(s_daily_fund.code,
                               next_trade_date,
                               position=positions):
                logger.debug("[%s]%s距离均线%.1f%%/%d个格,低于上次历史%.1f%%,买入%.1f份  基<---钱",
                             date2str(today),
                             s_daily_fund.code,
                             s_daily_fund.diff_percent * 100,
                             grid_num,
                             self.last_grid_position_dict[s_daily_fund.code] * 100,
                             positions)
                self.last_grid_position_dict[s_daily_fund.code] = - grid_num * self.grid_height_dict[s_daily_fund.code]

        # 在均线之上，且，超过之前的高度(diff>0)，且，至少超过1个网格(grid_num>=1)，就卖
        if s_daily_fund.diff_percent > 0 and diff > 0 and grid_num > 1:
            positions = self.policy.calculate(s_daily_fund.code, grid_num)
            # 扣除手续费后，下取整算购买份数
            if self.broker.sell(s_daily_fund.code, next_trade_date, position=positions):
                logger.debug(">>[%s]%s距离均线%.1f%%/%d个格,高于上次历史%.1f%%,卖出%.1f份  基===>钱",
                             date2str(today),
                             s_daily_fund.code,
                             s_daily_fund.diff_percent * 100,
                             grid_num,
                             self.last_grid_position_dict[s_daily_fund.code] * 100,
                             positions)
                self.last_grid_position_dict[s_daily_fund.code] = grid_num * self.grid_height_dict[s_daily_fund.code]
