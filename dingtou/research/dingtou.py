from __future__ import (absolute_import, division, print_function, unicode_literals)

import argparse
import os
import akshare as ak
import backtrader as bt
import pandas as pd
import tushare as ts
import backtrader.analyzers as btanalyzers

"""
测试定投效果:
1、用250线当分割线，跌破才启动买
2、越跌越买，比例由映射表决定
3、买的时机是至少要大于2周（10个交易日），且，当天下跌大于1个标准差，或者50%的百分位
   或者，2周的累计下跌大于多少？？？
4、计算好总仓位，投资周期在3~5年，所以要计算好弹药

参考：
- https://juejin.cn/post/6844903998793728007
"""


class TradeSizer(bt.Sizer):
    params = (('stake', 1),)

    def _getsizing(self, comminfo, cash, data, isbuy):
        if isbuy:
            return self.p.stake
        position = self.broker.getposition(data)
        if not position.size:
            return 0
        else:
            return position.size
        return self.p.stake


class TestStrategy(bt.Strategy):
    params = (('maperiod', 15), ('printlog', False),)
    plotinfo = dict(subplot=False)
    plotlines = dict(
        buy=dict(marker='^', markersize=8.0, color='red', fillstyle='full'),
        sell=dict(marker='v', markersize=8.0, color='lime', fillstyle='full')
    )

    def log(self, txt, dt=None, doprint=False):
        if self.params.printlog or doprint:
            dt = dt or self.datas[0].datetime.date(0)
            print('%s, %s' % (dt.isoformat(), txt))

    def __init__(self):

        self.dataclose = self.datas[0].close
        self.datahigh = self.datas[0].high
        self.datalow = self.datas[0].low

        self.order = None
        self.buyprice = 0
        self.buycomm = 0
        self.newstake = 0
        self.buytime = 0

        self.sma = bt.indicators.SMA(self.datahigh(-1), period=250, subplot=False, plotname='Upper')
        self.cross = bt.ind.CrossOver(self.dataclose(0), self.sma, plot=False)
        self.percent = bt.ind.DivByZero(self.sma, self.dataclose)

        self.POSITION = {

        }

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(
                    'BUY EXECUTED, Price: %.2f, Cost: %.2f, Comm %.2f' %
                    (order.executed.price,
                     order.executed.value,
                     order.executed.comm), doprint=True)
                self.buyprice = order.executed.price
                self.buycomm = order.executed.comm
            else:
                self.log('SELL EXECUTED, Price: %.2f, Cost: %.2f, Comm %.2f' %
                         (order.executed.price,
                          order.executed.value,
                          order.executed.comm), doprint=True)
                self.bar_executed = len(self)
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('Order Canceled/Margin/Rejected')
        self.order = None

    def notify_trade(self, trade):
        if not trade.isclosed:
            return
        self.log('OPERATION PROFIT, GROSS %.2f, NET %.2f' % (trade.pnl, trade.pnlcomm))

    def next(self):
        if self.order:
            return
            # 入场
        if self.cross > 0 and self.buytime == 0:
            self.newstake = self.broker.getvalue() * 0.01 / self.ATR
            self.newstake = int(self.newstake / 100) * 100
            self.sizer.p.stake = self.newstake
            self.buytime = 1
            self.order = self.buy()
            # 加仓
        elif self.datas[0].close > self.buyprice + 0.5 * self.ATR[0] and self.buytime > 0 and self.buytime < 5:
            self.newstake = self.broker.getvalue() * 0.01 / self.ATR
            self.newstake = int(self.newstake / 100) * 100
            self.sizer.p.stake = self.newstake
            self.order = self.buy()
            self.buytime = self.buytime + 1
            # 出场
        elif self.CrossoverLo < 0 and self.buytime > 0:
            self.order = self.sell()
            self.buytime = 0
            # 止损
        elif self.datas[0].close < (self.buyprice - 2 * self.ATR[0]) and self.buytime > 0:
            self.order = self.sell()
            self.buytime = 0


def aquire_baseline_data(code, start_date, end_date):
    index_file = f"{code}.csv"
    if not os.path.exists(index_file):
        df = ak.stock_zh_index_daily(symbol=code)
        df.to_csv(index_file)
    else:
        df = pd.read_csv(index_file)

    dates = pd.to_datetime(df['date'], format='%Y-%m-%d')
    df = df[['open', 'high', 'low', 'close', 'vol']]
    df.columns = ['open', 'high', 'low', 'close', 'volume']
    df.index = dates
    df.sort_index(ascending=True, inplace=True)

    print(df)
    print(code,start_date,end_date)

    return df

"""
指数代码：https://q.stock.sohu.com/cn/zs.shtml

SH000001: 上证指数
SH000300: 沪深300
SH000016：上证50
SH000905：中证500
SH000906：中证800
SH000852：中证1000

python dingtou.py -c 000831.SZ -s 20150101 -e 20220101 -b SH000905
"""
if __name__ == '__main__':

    cerebro = bt.Cerebro()

    cerebro.addstrategy(TestStrategy)

    parser = argparse.ArgumentParser()

    # 数据相关的
    parser.add_argument('-s', '--start_date', type=str, default="20150101", help="开始日期")
    parser.add_argument('-e', '--end_date', type=str, default="20221101", help="结束日期")
    parser.add_argument('-b', '--baseline', type=str, help="基准指数")
    parser.add_argument('-c', '--code', type=str, help="股票代码")

    args = parser.parse_args()
    df = aquire_baseline_data(args.baseline, args.start_date, args.end_date)

    data = bt.feeds.PandasData(dataname=df)
    cerebro.adddata(data)

    cerebro.broker.setcash(1000000.0)
    cerebro.broker.setcommission(commission=0.0012)

    cerebro.addsizer(TradeSizer)
    cerebro.addanalyzer(btanalyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(btanalyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(btanalyzers.Returns, _name='returns')
    begin = cerebro.broker.getvalue()
    result = cerebro.run()
    end = cerebro.broker.getvalue()
    print(f'初始仓位：{begin} 元')
    print(f'最终仓位：{round(end, 2)} 元')
    print('----------------------------')
    print(f'总收益:    {round(((end - begin) / begin) * 100, 2)}%')
    print(f"年化收益:  {round(result[0].analyzers.returns.get_analysis()['rnorm100'], 2)}%")
    print(f"最大回撤:  {round(result[0].analyzers.drawdown.get_analysis()['max']['drawdown'], 2)}%")
    try:
        print(f"夏普比率:  {round(result[0].analyzers.sharpe.get_analysis()['sharperatio'], 2)}")
    except:
        pass

    cerebro.plot(style='candle', iplot=False)
