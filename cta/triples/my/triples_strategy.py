import logging

import talib

from backtest.strategy import Strategy
from utils.utils import date2str

logger = logging.getLogger(__name__)


class TripleStrategy(Strategy):

    def __init__(self, broker, atr, ema):
        super().__init__(broker, None)
        self.atr = atr
        self.ema = ema

    def set_data(self, df_dict: dict, df_baseline=None):
        super().set_data(df_baseline, df_dict)
        df_flow = df_dict['moneyflow_hsgt']

        """
        https://tushare.pro/document/2?doc_id=47
        north_money	float	北向资金（百万元）
        south_money	float	南向资金（百万元）
        
        中轨线 = 90日的移动平均线（SMA)
        上轨线 = 90日的SMA +（90日的标准差 x 2）
        下轨线 = 90日的SMA -（90日的标准差 x 2）
        """
        df_flow['net_amount'] = df_flow.north_money - df_flow.south_money
        df_flow['mid'] = talib.SMA(df_flow.net_amount, timeperiod=90)
        df_flow['std'] = talib.STDDEV(df_flow.net_amount, timeperiod=90, nbdev=1)
        df_flow['upper'] = df_flow.mid + 2 * df_flow.std
        df_flow['lower'] = df_flow.mid - 2 * df_flow.std


    def next(self, today, trade_date):
        super().next(today, trade_date)

        for code, df in self.df_dict.items():

            s = self.get_value(df, today)
            if s is None: continue

            # 如果空仓
            if not self.get_position(code) or self.get_position(code).position == 0:
                if s.close > s.upper:
                    self.broker.buy(code, trade_date, amount=10000)
                    logger.debug('[%r] 挂买单，股票[%s]/目标日期[%s]', date2str(today), code, date2str(trade_date))
            # 如果持仓
            else:
                if s.close < s.lower:
                    logger.debug('[%r] 挂卖单，股票[%s]/目标日期[%s]', date2str(today), code, date2str(trade_date))
                    self.broker.sell_out(code, trade_date)
