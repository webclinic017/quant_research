import logging

import pandas as pd

from backtest.strategy import Strategy
from utils.utils import date2str

logger = logging.getLogger(__name__)


class BollingStrategy(Strategy):

    def __init__(self, broker, params):
        super().__init__(broker, None)
        self.params = params
        self.df_position = pd.DataFrame()

    def set_data(self, df_dict: dict, df_baseline=None):
        super().set_data(df_baseline, df_dict)
        self.df = df_dict[self.params.code]
        self.code = self.params.code

    def next(self, today, trade_date):
        super().next(today, trade_date)
        s_today = self.get_value(self.df, today)

        # 不是交易日数据，忽略
        if s_today is None: return

        position = self.broker.get_position(self.code)
        if not position and s_today.close > s_today.upper:
            if not self.broker.get_position(self.code):
                self.broker.buy(self.code, trade_date, amount=self.broker.total_cash)
                logger.debug("[%s] [%s] close[%.4f] > upper[%.4f], 买入",
                             date2str(today), self.code, s_today.close, s_today.upper)
                return

        sell_threshold = s_today.middle if self.params.sell_flag=='middle' else s_today.lower
        if position and s_today.close < sell_threshold:
            if self.broker.get_position(self.code):
                logger.debug("[%s] [%s] close[%.4f] < middle[%.4f], 卖出",
                             date2str(today), self.code, s_today.close, s_today.middle)
                self.broker.sell_out(self.code, trade_date)
                return

        # 如果持仓，看是否到止损，到止损，就需要卖出清仓了
        # 按理说应该是盘中止损，但是，我的框架模拟不出来，只好第二天再止损
        # 看今天的收盘价已经超过损失了
        if position:
            loss = (s_today.close - position.cost) / position.cost
            # loss和阈值都是负的，所以要小于阈值
            if loss < self.params.limit_loss:
                logger.warning("[%s] [%s]今日价格[%.4f]对比成本[%.4f]，损失超过[%.2f%%]，止损清仓",
                               date2str(today), self.code, s_today.close, position.cost, loss * 100)
                self.broker.sell_out(self.code, trade_date)
