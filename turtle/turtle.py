from __future__ import (absolute_import, division, print_function, unicode_literals)

import argparse

import backtrader as bt
import pandas as pd
import tushare as ts
import backtrader.analyzers as btanalyzers

"""
参考：
- https://mp.weixin.qq.com/s/wYwkG1MlGb-d4YAuWNR_nQ
- https://zhuanlan.zhihu.com/p/27987938
- 《迭代式的量化策略研发》- 第7课
唐奇安通道的各项指标的计算方法为：
    上轨 = Max（最高低，n）, n日最高价的最大值
    下轨 = Min（最低价，n）, n日最低价的最小值
    中轨 = (上轨+下轨)/2
什么时候加仓
    如果开的底仓是多仓且资产的价格在上一次建仓（或者加仓）的基础上又上涨了0.5N，就再加一个Unit的多仓；
什么时候止盈：
    如果开的底仓是多仓且当前资产价格跌破了10日唐奇安通道的下轨，就清空所有头寸结束策略；
什么时候止损
    如果开的底仓是多仓且资产的价格在上一次建仓（或者加仓）的基础上又下跌了2N，就卖出全部头寸止损；
特点：
    大趋势中十分强劲，在震荡市中表现不如人意 
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
        # 参数计算，唐奇安通道上轨、唐奇安通道下轨、ATR
        self.DonchianHi = bt.indicators.Highest(self.datahigh(-1), period=20, subplot=False, plotname='Upper')
        self.DonchianLo = bt.indicators.Lowest(self.datalow(-1), period=10, subplot=False, plotname='Lower')
        self.TR = bt.indicators.Max((self.datahigh(0) - self.datalow(0)),
                                    abs(self.dataclose(-1) - self.datahigh(0)),
                                    abs(self.dataclose(-1) - self.datalow(0)))
        self.ATR = bt.indicators.SimpleMovingAverage(self.TR, period=14, plot=False)
        # 唐奇安通道上轨突破、唐奇安通道下轨突破
        self.CrossoverHi = bt.ind.CrossOver(self.dataclose(0), self.DonchianHi, plot=False)
        self.CrossoverLo = bt.ind.CrossOver(self.dataclose(0), self.DonchianLo, plot=False)

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
        if self.CrossoverHi > 0 and self.buytime == 0:
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


def aquire_data(stock, start_date, end_date):
    print(stock,start_date,end_date)
    df = ts.pro_bar(ts_code=stock, adj='hfq', start_date=start_date, end_date=end_date)
    dates = pd.to_datetime(df["trade_date"])
    df = df[['open', 'high', 'low', 'close', 'vol']]
    df.columns = ['open', 'high', 'low', 'close', 'volume']
    df.index = dates
    df.sort_index(ascending=True, inplace=True)
    return df

"""
python turtle.py -c 000831.SZ -s 20150101 -e 20220101
结果：
    初始仓位：1000000.0 元
    最终仓位：2391579.53 元
    ----------------------------
    总收益:    139.16%
    年化收益:  13.8%
    最大回撤:  23.5%
    夏普比率:  0.52
"""
if __name__ == '__main__':

    cerebro = bt.Cerebro()

    cerebro.addstrategy(TestStrategy)

    token = open("token", "r").readline()
    print(f"token: {token}")
    ts.set_token(token)
    # ts.set_token('输入你的Tushare Token')
    parser = argparse.ArgumentParser()

    # 数据相关的
    parser.add_argument('-s', '--start_date', type=str, default="20150101", help="开始日期")
    parser.add_argument('-e', '--end_date', type=str, default="20221101", help="结束日期")
    parser.add_argument('-c', '--code', type=str, help="股票代码")

    args = parser.parse_args()
    df = aquire_data(args.code, args.start_date, args.end_date)

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
