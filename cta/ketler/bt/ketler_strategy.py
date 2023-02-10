import datetime
import logging

import backtrader as bt

from bt.AmarketSizer import AMarketSize
from ketler.bt.ketler_indicator import Ketler
from utils import utils

logger = logging.getLogger(__name__)


class KetlerStrategy(bt.Strategy):

    def __init__(self):
        # 凯特勒指标
        self.ketler = Ketler(self.data, plot=True)
        # 自定义的一个sizer，用于应对A股整手的限制
        self.sizer = AMarketSize()

    def _date(self):
        """用于显示今日日期用"""
        stock_day_date = self.datas[0].datetime.datetime(0)
        return utils.date2str(stock_day_date)

    def next(self):
        """核心方法，用于书写策略"""

        # 如果空仓,收盘价突破凯特勒上轨,尝试买入
        if self.getposition(self.data).size == 0:
            if self.data.close[0] > self.ketler.upper[0]:

                # 买入市价单，有效期1天
                self.buy(data=self.data,
                         exectype=bt.Order.Market,
                         valid=datetime.datetime.now() + datetime.timedelta(days=1))

                logger.debug('[%r] 尝试买入: 股票[%s]，今日收盘[%.2f]',
                             self._date(),
                             self.data._name,
                             self.data.close[0])
        # 如果持仓，且收盘价跌破凯特勒下轨，就卖出
        else:
            if self.data.close[0] < self.ketler.lower[0]:
                logger.debug('[%r] 尝试卖出: 股票[%s]',
                             utils.date2str(self.data.datetime.datetime(0)), self.data._name)
                # 全部清仓
                self.order = self.close()

    def notify_order(self, order):
        """用于监控订单的状态变化，是一个回调函数"""

        # 如果order为submitted/accepted,返回空
        if order.status in [order.Submitted, order.Accepted]:
            # logger.debug('[%r] 股票[%s]订单%s,价格[%.2f],股数[%.1f],手续费[%1.f],合计[%.1f]',
            #              utils.date2str(bt.num2date(order.created.dt)),
            #              order.data._name,
            #              order.Status[order.status],
            #              order.created.price,
            #              order.created.size,
            #              order.executed.comm,
            #              order.executed.comm + order.created.price * order.created.size
            #              )
            return

        # 如果order为buy/sell executed,报告价格结果
        if order.status in [order.Completed]:
            if order.isbuy():
                logger.debug('[%r] 成功买入: 股票[%s],价格[%.2f],价值[%.2f],手续费[%.2f]',
                             utils.date2str(bt.num2date(order.executed.dt)),
                             order.data._name,
                             order.executed.price,
                             order.executed.value,
                             order.executed.comm)
                self.buyprice = order.executed.price
                self.buycomm = order.executed.comm

            if order.issell():
                logger.debug('[%r] 成功清仓: 股票[%s],价格[%.2f],价值[%.2f],手续费[%.2f]',
                             utils.date2str(bt.num2date(order.executed.dt)),
                             order.data._name,
                             order.executed.price,
                             order.executed.value,
                             order.executed.comm)
                # 卖出后，重新更新整体值
                self.value_last = self.broker.get_value()
                cash = self.broker.get_cash()
                logger.debug("清仓后，持有现金：%.2f,真实现金和持仓[%.2f/%.2f]" %
                             (self.value_last, cash, self.value_last - cash))

            self.bar_executed = len(self)

        # 如果指令取消/交易失败, 报告结果
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            # import pdb;pdb.set_trace()
            logger.warning('[%r] 交易失败，股票[%s]订单状态：%r,价格[%.2f],股数[%.1f]',
                         utils.date2str(bt.num2date(order.executed.dt)),
                         order.data._name,
                         order.Status[order.status],
                         order.created.price,
                         order.created.size)

        self.order = None

    # 这个是一只股票的一个完整交易的生命周期：开仓，持有，卖出
    def notify_trade(self, trade):
        """用于跟踪一个完整交易"""

        if trade.isclosed:
            open_date = utils.date2str(bt.num2date(trade.dtopen))
            close_date = utils.date2str(bt.num2date(trade.dtclose))
            logger.debug('[%s]~[%s] 持仓%d交易日，策略收益：股票[%s], 毛收益 [%.2f], 净收益 [%.2f]',
                         open_date,
                         close_date,
                         trade.barlen,
                         trade.data._name,
                         trade.pnl,
                         trade.pnlcomm,
                         )
            logger.debug("-" * 80)
