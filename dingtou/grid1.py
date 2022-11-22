import backtrader as bt

import pandas as pd
import numpy as np
import argparse, os
import akshare as ak
from backtrader_plotting import Bokeh
from backtrader_plotting.schemes import Tradimo

"""
在上面的网格交易里我们是先确定最大值和最小值，在这里我编程的时候先算出中间值，
然后从中间值往上下，价格每改变 0.5% 画一个格子，这样的好处是为了应对过高的手续费问题，
如果我们的格子太小，就 cover 不住手续费，
如果我们以格子宽度做为参数那我们可以通过调节宽度来一定程度上应对手续费问题。
但整体逻辑是一样的，这就好比 距离(高低点差) = 速度(格子宽度) x 时间(格子数量)，
我们可以任选两个变量从而确定第三个值。

"""
P_BACKDAYS = 250
P_GRID_NUM = 10
P_GRID_SCOPE = 0.1
P_GRID_ONE = P_GRID_SCOPE / P_GRID_NUM


class AStockPlotScheme(Tradimo):
    """
    自定义的bar和volumn的显示颜色，follow A股风格
    """

    def _set_params(self):
        super()._set_params()
        self.barup = "#FC5D45"
        self.bardown = "#009900"
        self.barup_wick = self.barup
        self.bardown_wick = self.bardown
        self.barup_outline = self.barup
        self.bardown_outline = self.bardown
        self.volup = self.barup
        self.voldown = self.bardown


def aquire_baseline_data(code, start_date, end_date):
    index_file = f"{code}.csv"
    if not os.path.exists(index_file):
        df = ak.stock_zh_index_daily(symbol=code)
        df.to_csv(index_file)
    else:
        df = pd.read_csv(index_file)

    dates = pd.to_datetime(df['date'], format='%Y-%m-%d')
    df = df[['open', 'high', 'low', 'close', 'volume']]
    df.columns = ['open', 'high', 'low', 'close', 'volume']
    df.index = dates
    df.sort_index(ascending=True, inplace=True)

    print(df)
    print(code, start_date, end_date)

    return df


class GridStrategy(bt.Strategy):

    def __init__(self):
        self.highest = bt.indicators.Highest(self.data.high, period=P_BACKDAYS, subplot=False)
        self.lowest = bt.indicators.Lowest(self.data.low, period=P_BACKDAYS, subplot=False)
        mid = (self.highest + self.lowest) / 2
        perc_levels = [x for x in np.arange(
            1 + P_GRID_SCOPE, 1 - P_GRID_SCOPE, -P_GRID_ONE)]
        self.price_levels = [mid * x for x in perc_levels]
        self.last_price_index = None

    def next(self):
        if self.last_price_index == None:
            for i in range(len(self.price_levels)):
                if self.data.close > self.price_levels[i]:
                    self.last_price_index = i
                    self.order_target_percent(
                        target=i / (len(self.price_levels) - 1))
                    return
        else:
            signal = False
            while True:
                upper = None  # n+1
                lower = None  # n-1
                if self.last_price_index > 0:
                    upper = self.price_levels[self.last_price_index - 1]
                if self.last_price_index < len(self.price_levels) - 1:
                    lower = self.price_levels[self.last_price_index + 1]
                # 还不是最轻仓，继续涨，就再卖一档
                if upper != None and self.data.close > upper:
                    self.last_price_index = self.last_price_index - 1
                    signal = True
                    continue
                # 还不是最重仓，继续跌，再买一档
                if lower != None and self.data.close < lower:
                    self.last_price_index = self.last_price_index + 1
                    signal = True
                    continue
                break
            if signal:
                self.long_short = None
                # order_target_percent函数是直接调整到目标仓位，相当好用，不用考虑买多少卖多少问题
                self.order_target_percent(
                    target=self.last_price_index / (len(self.price_levels) - 1))


"""
指数代码：https://q.stock.sohu.com/cn/zs.shtml

SH000001: 上证指数
SH000300: 沪深300
SH000016：上证50
SH000905：中证500
SH000906：中证800
SH000852：中证1000

python grid1.py -c 000831.SZ -b SH000905 -s 20150101 -e 20220101
"""
if __name__ == '__main__':
    # 获得数据
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--start_date', type=str, default="20150101", help="开始日期")
    parser.add_argument('-e', '--end_date', type=str, default="20221101", help="结束日期")
    parser.add_argument('-b', '--baseline', type=str, help="基准指数")
    parser.add_argument('-c', '--code', type=str, help="股票代码")
    args = parser.parse_args()
    df = aquire_baseline_data(args.baseline, args.start_date, args.end_date)

    # 创建引擎
    cerebro = bt.Cerebro()

    # 加入网格策略
    cerebro.addstrategy(GridStrategy)

    # 导入数据
    data = bt.feeds.PandasData(dataname=df,
                               timeframe=bt.TimeFrame.Days,
                               openinterest=-1)

    cerebro.resampledata(data, timeframe=bt.TimeFrame.Weeks, name="dingtou")

    # 设置起始资金
    cerebro.broker.setcash(10000000.0)

    # # 设定对比指数
    # cerebro.addanalyzer(bt.analyzers.TimeReturn,
    #                     timeframe=bt.TimeFrame.Years,
    #                     data=data, _name='benchmark')

    # 策略收益
    cerebro.addanalyzer(bt.analyzers.TimeReturn,
                        timeframe=bt.TimeFrame.Years,
                        _name='portfolio')

    start_value = cerebro.broker.getvalue()
    print('Starting Portfolio Value: %.2f' % start_value)

    # Run over everything
    results = cerebro.run()

    strat0 = results[0]
    tret_analyzer = strat0.analyzers.getbyname('portfolio')
    # print('Portfolio Return:', tret_analyzer.get_analysis())
    # tdata_analyzer = strat0.analyzers.getbyname('benchmark')
    # print('Benchmark Return:', tdata_analyzer.get_analysis())

    # 画图
    # cerebro.plot(style='candle', barup='green')

    # 运行回测
    results = cerebro.run(optreturn=True)

    if not os.path.exists(f"debug/"): os.makedirs(f"debug/")
    file_name = f"debug/report.html"

    b = Bokeh(filename=file_name,
              style='bar',
              plot_mode='single',
              output_mode='save',
              scheme=AStockPlotScheme())
    cerebro.plot(b, style='candlestick', iplot=False)
