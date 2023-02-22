import logging

import talib
import numpy as np
from utils.utils import OLS

logger = logging.getLogger(__name__)


def macd(df, params):
    macd = talib.MACD(df['close'],
                      fastperiod=params.fastperiod,
                      slowperiod=params.slowperiod,
                      signalperiod=params.signalperiod)
    df["macd"], df["macd_signal"], df["macd_hist"] = macd
    df['ma5'] = talib.SMA(df.close, 5)
    df['ma10'] = talib.SMA(df.close, 10)
    df['ma20'] = talib.SMA(df.close, 20)
    df['slope'] = claculate_slope(df.close, params)
    df['rsi'] = talib.RSI(df.close)
    return df


def claculate_slope(close, params):
    def claculate_one_slope(close):
        """计算10天内的直线拟合斜率"""
        X = np.linspace(0, close.max()-close.min(), len(close))
        params, r2 = OLS(X, close)
        beta = params[1]
        return beta

    # 先计算10天窗口期内的斜率
    s = close.rolling(window=params.slope_windows).apply(claculate_one_slope)
    return s
