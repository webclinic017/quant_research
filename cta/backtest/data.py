import logging

import talib

from utils.data_loader import load_stock, load_index

logger = logging.getLogger(__name__)
class BaseData():
    def process(self, df, params):
        raise NotImplemented("没实现")

    def prepare(self, params):
        df_dict = {}
        df_baseline = load_index(index_code=params.baseline)
        codes = params.code.split(",") if "," in params.code else [params.code]
        for code in codes:
            df = load_stock(code, adjust='hfq')
            df = self.process(df, params)
            df_dict[code] = df

        return df_baseline,df_dict


