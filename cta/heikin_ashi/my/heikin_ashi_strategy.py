import logging

import pandas as pd

from backtest.strategy import Strategy
from utils import utils
from utils.utils import date2str

logger = logging.getLogger(__name__)


class HeikinAshiStrategy(Strategy):

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

        # 今天是0，昨天是1，前天是2
        s0 = self.get_value(self.df, today)
        # 不是交易日数据，忽略
        if s0 is None: return
        s1 = utils.get_series(self.df, today, -1)
        s2 = utils.get_series(self.df, today, -2)

        # 前天的eam3和eam8的距离
        gap2 = s2.ema3 - s2.ema8
        # 昨天的eam3和eam8的距离
        gap1 = s1.ema3 - s1.ema8
        gap_percent = gap1 / gap2

        position = self.broker.get_position(self.code)

        """
        前天是多头排列（ema3>ema8>ema17)
        昨天是多头排列（ema3>ema8>ema17)
        昨天回撤：昨天s1.ema3< 前天s2.ema3
        昨天是回撤，回撤距离大于0.5，
        今天是多头排列（ema3>ema8>ema17)
        今天的收盘价高于ema3
        """
        if not position and \
                s2.ema17 < s2.ema8 < s2.ema3 and \
                s1.ema17 < s1.ema8 < s1.ema3 < s2.ema3 and \
                s0.ema17 < s0.ema8 < s0.ema3 and \
                gap_percent < 0.5 and \
                s0.h_close > s0.ema3:
            self.broker.buy(self.code, trade_date, amount=self.broker.total_cash)
            logger.debug("[%s] [%s] 信号满足, 买入", date2str(today), self.code)
            return

        # 如果持仓，看是否到止损，到止损，就需要卖出清仓了
        # 按理说应该是盘中止损，但是，我的框架模拟不出来，只好第二天再止损
        # 看今天的收盘价已经超过损失了
        if position:
            # profit and loss
            pnl = (s0.close - position.cost) / position.cost
            # 止损：loss和阈值都是负的，所以要小于阈值
            if pnl < self.params.limit_loss:
                logger.warning("[%s] [%s]今日价格[%.4f]对比成本[%.4f]，损失超过[%.2f%%]，止损清仓",
                               date2str(today), self.code, s0.close, position.cost, pnl * 100)
                self.broker.sell_out(self.code, trade_date)
            # 止盈
            if pnl > self.params.limit_win:
                logger.warning("[%s] [%s]今日价格[%.4f]对比成本[%.4f]，盈利超过[%.2f%%]，止盈清仓",
                               date2str(today), self.code, s0.close, position.cost, pnl * 100)
                self.broker.sell_out(self.code, trade_date)
