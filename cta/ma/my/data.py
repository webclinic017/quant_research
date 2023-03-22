import logging

import talib

from ma.my.rolling_max_drawdown import rolling_max_dd
from utils.data_loader import load_stock, load_index

logger = logging.getLogger(__name__)


class Data():
    def process(self, df, params):
        if params.k_type == 'heikin-ashi':
            df['close'] = (df.high + df.low + df.open + df.close) / 4
        df["ma"] = talib.SMA(df.close,timeperiod=params.ma)
        df["max_drawdown"] = rolling_max_dd(df.close.pct_change(),window_size=params.max_drawdown_windows_size) # 120天内的最大回撤
        return df

    def prepare(self, params):
        df_dict = {}
        df_baseline = load_index(index_code=params.baseline)
        codes = params.code.split(",") if "," in params.code else [params.code]
        for code in codes:
            df = load_stock(code, adjust='hfq')
            df = self.process(df, params)
            df_dict[code] = df

        return df_baseline, df_dict
