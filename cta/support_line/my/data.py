import logging

import talib

from backtest.data import BaseData
from utils.data_loader import load_stock, load_index

logger = logging.getLogger(__name__)

"""
# 平均K线图（Heikin-Ashi）

![img50](/images/20230223/1677130895050.jpg)

计算方法:

假设普通蜡烛图的**今天**的开市价、最高价、最低价及收盘价则简称为：O、H、L、C，**昨日**收盘价为：C'

假设平均K线图的**今天**的开市价、最高价、最低价及收盘价为：open、high、low、close，**昨日**收盘价为：open'

那么，他们的之间的关系为：

$$

\begin{align*}

& open =  \frac{open'+close'}{2} \\

& close =  \frac{O+H+L+C}{4} \\

& high =  \max(H,open,close) \\

& low =  \min(L,open,close)

\end{align*}
$$

解释：

- 平均k线的开盘价 = 是昨天平均k线开、昨日普通k线收的平均（注意！开用的是平均k线的）
- 平均k线的收盘价 = 今天普通k线开、普通k线收、普通k线高、普通k线低的平均
- 平均k线的最高价 = 是今天普通k线高、平均k线开、平均k线收，取最大
- 平均k线的最低价 = 是今天普通k线低、平均k线开、平均k线收，取最小

好处：
- 图表看起来更“平滑”
- 

直观感受一下：

![img50](/images/20230223/1677133008895.jpg)

注意：
- 由于平均K线图（Heikin-Ashi）取的是平均值，因此K线显示的当前价格可能与市场实际交易价格是不一致的

实现：
- https://towardsdatascience.com/how-to-calculate-heikin-ashi-candles-in-python-for-trading-cff7359febd7
- https://stackoverflow.com/questions/40613480/heiken-ashi-using-pandas-python
"""


class Data(BaseData):

    def process(self, df, params):
        """
        - 平均k线的开盘价 = 是昨天平均k线开、昨日普通k线收的平均（注意！开用的是平均k线的）
        - 平均k线的收盘价 = 今天普通k线开、普通k线收、普通k线高、普通k线低的平均
        - 平均k线的最高价 = 是今天普通k线高、平均k线开、平均k线收，取最大
        - 平均k线的最低价 = 是今天普通k线低、平均k线开、平均k线收，取最小
        """

        def calc_h_open(s):
            # 开盘,s.index会有2个index，分别是昨日和今日，取昨日的，计算出当日的open，返回
            s = df.loc[s.index, ['h_open', 'h_close']].iloc[0] # 0是昨天，1是今天
            return (s.h_close + s.h_open) / 2
        # 收盘
        df["h_close"] = (df.high + df.low + df.open + df.close) / 4
        df["h_open"] = df.open  # 默认先给个值
        # 开盘
        df['h_open'] = df.close.rolling(window=2).apply(calc_h_open, raw=False) # raw=False返回一个sub-dataframe
        # 最高
        df['h_high'] = df[["high", "h_open", "h_close"]].max(axis=1) # axis=1是行里挑最大最小
        # 最低
        df['h_low'] = df[["low", "h_open", "h_close"]].min(axis=1)

        df['ema3'] = talib.EMA(df.h_close,3)
        df['ema8'] = talib.EMA(df.h_close, 8)
        df['ema17'] = talib.EMA(df.h_close, 17)

        return df


# python -m heikin_ashi.my.data
if __name__ == '__main__':
    df = load_stock('600196')
    print(Data().process(df))
    # print(df.rolling(7).mean())
