import logging

import talib

from backtest.strategy import Strategy
from utils.utils import date2str

logger = logging.getLogger(__name__)


class KelterStrategy(Strategy):

    def __init__(self, broker, atr, ema):
        super().__init__(broker, None)
        self.atr = atr
        self.ema = ema

    def set_data(self, df_dict: dict, df_baseline=None):
        super().set_data(df_baseline, df_dict)
        for code, df in df_dict.items():
            print(df)
            df['expo'] = talib.EMA(df.close, timeperiod=self.ema)
            df['atr'] = talib.ATR(df.high, df.low, df.close, timeperiod=self.atr)
            df['upper'] = df.expo + df.atr
            df['lower'] = df.expo - df.atr

    def next(self, today, trade_date):
        super().next(today, trade_date)

        b_flag = False
        for code, df in self.df_dict.items():

            s = self.get_value(df, today)
            if s is None: continue

            # 如果空仓
            if not self.get_position(code) or self.get_position(code).position == 0:
                if s.close > s.upper:
                    if self.broker.buy(code, trade_date, amount=self.broker.total_cash):
                        logger.debug('[%r] 挂买单，股票[%s]/目标日期[%s]', date2str(today), code, date2str(trade_date))
                        b_flag = True
            # 如果持仓
            else:
                if s.close < s.lower:
                    if self.broker.sell_out(code, trade_date):
                        logger.debug('[%r] 挂卖单，股票[%s]/目标日期[%s]', date2str(today), code, date2str(trade_date))
                        b_flag = True

        return b_flag