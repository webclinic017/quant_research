import logging

import pandas as pd

from backtest.strategy import Strategy
from utils.utils import date2str

logger = logging.getLogger(__name__)


class MACDStrategy(Strategy):

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
        """
        - 找到第一个变小的绿柱，挂买单
        - 找到第一个变小的红柱，挂买单
        - 每天监控收盘和最低，如果止损，就挂买单
        
        后续：
        - 考虑面积、分位数
        - 考虑斜率、连续数量
        - 考虑前一天的涨跌
        """
        df = self.df
        code = self.code
        s_today = self.get_value(df, today)

        # 不是交易日数据，忽略
        if s_today is None: return

        # import pdb;pdb.set_trace()

        today_macd = s_today.macd_hist
        today_slope = s_today.slope
        today_loc = df.index.get_loc(today)
        s_yesterday = df.iloc[today_loc - 1]
        yesterday_macd = s_yesterday.macd_hist
        yesterday = s_yesterday._name

        # print(today_loc,yesterday,yesterday_macd," vs ",today,today_macd)

        # 绿柱变小，上升趋势，考虑买入
        if today_macd < 0 and today_macd > yesterday_macd and s_today.rsi<=30:
            #and today_slope > self.params.slope_threshold:
            if self.broker.get_position(code):
                logger.debug("今日[%s]macd[%.4f] > 昨日[%s]macd[%.4f]，但是由于持仓[%s]，忽略买点",
                             date2str(today), today_macd,
                             date2str(yesterday), yesterday_macd,
                             code)
                return

            self.broker.buy(code, trade_date, amount=self.broker.total_cash)
            logger.debug("今日[%s]macd[%.4f] > 昨日[%s]macd[%.4f]，20日均线斜率[%.2f],买入[%s]",
                         date2str(today), today_macd,
                         date2str(yesterday), yesterday_macd,
                         today_slope,
                         code)
            return
            # TODO，当日可以买回

        position = self.broker.get_position(code)
        # 如果持仓，绿柱变大，判断失败（应该是一路变小，然后翻红，直至红柱变小），应该卖出
        if position and today_macd < 0 and today_macd < yesterday_macd:
            self.broker.sell_out(code, trade_date)
            logger.debug("今日[%s]macd[%.4f] < 昨日[%s]macd[%.4f](绿柱变高)，清仓[%s]",
                         date2str(today), today_macd,
                         date2str(yesterday), yesterday_macd,
                         code)
            return



        # 红柱变小，准备卖出
        if position and today_macd >= 0 and today_macd < yesterday_macd:
            self.broker.sell_out(code, trade_date)
            logger.debug("今日[%s]macd[%.4f] < 昨日[%s]macd[%.4f](红柱变低)，清仓[%s]",
                         date2str(today), today_macd,
                         date2str(yesterday), yesterday_macd,
                         code)
            return

        # 如果持仓，看是否到止损，到止损，就需要卖出清仓了
        # 按理说应该是盘中止损，但是，我的框架模拟不出来，只好第二天再止损
        # 看今天的收盘价已经超过损失了
        if position:
            loss = (s_today.close - position.cost)/position.cost
            # loss和阈值都是负的，所以要小于阈值
            if loss < self.params.limit_loss:
                logger.warning("[%s] [%s]今日价格[%.4f]对比成本[%.4f]，损失超过[%.2f%%]，止损清仓",
                               date2str(today),code,s_today.close,position.cost,loss*100)
                self.broker.sell_out(code,trade_date)

