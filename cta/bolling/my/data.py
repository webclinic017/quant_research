import logging

import talib

from utils.data_loader import load_stock, load_index

logger = logging.getLogger(__name__)


class Data():
    def process(self, df, params):
        if params.k_type == 'heikin-ashi':
            close = (df.high + df.low + df.open + df.close) / 4
        else:
            close = df.close

        df["upper"], df["middle"], df["lower"] = \
            talib.BBANDS(close,
                         timeperiod=params.bolling_ma,
                         nbdevup=params.bolling_std,
                         nbdevdn=params.bolling_std,
                         matype=0)
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
