from dingtou.backtest.strategy import Strategy
from dingtou.utils.utils import get_value, date2str
import logging
import talib
import pandas as pd

logger = logging.getLogger(__name__)


class PyramidStrategy(Strategy):
    """
    """

    def __init__(self, broker, policy, up_grid_height_dict, down_grid_height_dict,ma_days):
        super().__init__(broker, None)
        self.up_grid_height_dict = up_grid_height_dict  # 上涨时候网格高度
        self.down_grid_height_dict = down_grid_height_dict  # 下跌网格高度
        self.policy = policy
        self.last_grid_position_dict = {}
        self.ma_days = ma_days

    def set_data(self, df_baseline, funds_dict: dict):
        super().set_data(df_baseline, funds_dict)
        for code, df_daily_fund in funds_dict.items():
            if self.ma_days <= 0:
                # 如果是self.ma_days是负值，回看前N天的最大最小值的中间值
                maxs = talib.MAX(df_daily_fund.close, timeperiod=-self.ma_days)
                mins = talib.MIN(df_daily_fund.close, timeperiod=-self.ma_days)
                df_daily_fund['ma'] = (maxs + mins) / 2
            else:
                # 如果是self.ma_days是正值，用N天的均线
                df_daily_fund['ma'] = talib.SMA(df_daily_fund.close, timeperiod=self.ma_days)
            df_daily_fund['diff_percent_close2ma'] = (df_daily_fund.close - df_daily_fund.ma) / df_daily_fund.ma
        for fund_code in funds_dict.keys():
            self.last_grid_position_dict[fund_code] = 0

    def next(self, today, trade_date):
        super().next(today, trade_date)

        # 遍历每一只基金，分别处理
        for fund_code, df_fund in self.funds_dict.items():
            self.handle_one_fund(df_fund, today, trade_date)

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
        if pd.isna(s_daily_fund.diff_percent_close2ma): return

        # 当前和上次位置的距离（单位是百分比）
        diff2last = s_daily_fund.diff_percent_close2ma - self.last_grid_position_dict[s_daily_fund.code]

        # 如果比之前的网格低"至少1个格子"，且在均线之下，就买入
        if s_daily_fund.diff_percent_close2ma < 0 and \
                diff2last < 0 and \
                abs(diff2last / self.down_grid_height_dict[s_daily_fund.code]) >= 1:
            # 计算这次下跌，距离均线的网格数
            grid_num = abs(round(s_daily_fund.diff_percent_close2ma / self.down_grid_height_dict[s_daily_fund.code]))
            positions = self.policy.calculate(s_daily_fund.code, grid_num)
            # 扣除手续费后，下取整算购买份数
            # 追加投资
            if self.broker.buy(s_daily_fund.code,
                               next_trade_date,
                               position=positions):
                logger.debug("[%s]%s距离均线%.1f%%/%d个格,低于上次历史%.1f%%,买入%.1f份  基<---钱",
                             date2str(today),
                             s_daily_fund.code,
                             s_daily_fund.diff_percent_close2ma * 100,
                             grid_num,
                             self.last_grid_position_dict[s_daily_fund.code] * 100,
                             positions)
                self.last_grid_position_dict[s_daily_fund.code] = - grid_num * self.down_grid_height_dict[
                    s_daily_fund.code]

        # 在均线之上，且，超过之前的高度(diff>0)，且，至少超过1个网格(grid_num>=1)，就卖
        if s_daily_fund.diff_percent_close2ma > 0 and \
                diff2last > 0 and \
                abs(diff2last / self.up_grid_height_dict[s_daily_fund.code]) >= 1:
            # 计算这次下跌，距离均线的网格数
            grid_num = abs(
                round(s_daily_fund.diff_percent_close2ma / self.up_grid_height_dict[s_daily_fund.code]))
            positions = self.policy.calculate(s_daily_fund.code, grid_num)
            # 扣除手续费后，下取整算购买份数
            if self.broker.sell(s_daily_fund.code, next_trade_date, position=positions):
                logger.debug(">>[%s]%s距离均线%.1f%%/%d个格,高于上次历史%.1f%%,卖出%.1f份  基===>钱",
                             date2str(today),
                             s_daily_fund.code,
                             s_daily_fund.diff_percent_close2ma * 100,
                             grid_num,
                             self.last_grid_position_dict[s_daily_fund.code] * 100,
                             positions)
                self.last_grid_position_dict[s_daily_fund.code] = grid_num * self.up_grid_height_dict[s_daily_fund.code]
