import datetime
import logging

import backtrader as bt

from bt.AmarketSizer import AMarketSize
from ketler.bt.ketler_indicator import Ketler
from utils import utils
from utils.utils import calc_size

logger = logging.getLogger(__name__)


class KetlerStrategy(bt.Strategy):

    def __init__(self):
        self.ketler = Ketler(self.data, plot=True)
        self.sizer = AMarketSize()

    def _date(self):
        stock_day_date = self.datas[0].datetime.datetime(0)
        return utils.date2str(stock_day_date)

    def next(self):

        s_date = utils.date2str(self.data.datetime.datetime(0))

        # 如果空仓,收盘价突破上轨,尝试买入
        if self.getposition(self.data).size == 0:
            if self.data.close[0] > self.ketler.upper[0]:
                # 防止涨停买入，把限价做到涨停价，再高就不买了，防止买入涨停
                limit_price = self.data.close[0] * 1.098
                # 计算当前可以买多少手，用的是今天的价格，来估计的，可能会有问题，因为真正成交是第二天的开盘价
                # 所以用limit_price，即把价格抬高一些，保证钱够
                commission = self.broker.getcommissioninfo(self.data).p.commission
                # size = calc_size(self.broker.get_cash(), limit_price, commission)
                # if size <= 0:
                #     logger.warning("[%s] 头寸分配失败，无法买入", s_date)
                #     return
                # 挂一个限价在1.098的限价单，超过就不买了，有效期1天
                self.buy(data=self.data,
                         exectype=bt.Order.Market,
                         valid=datetime.datetime.now() + datetime.timedelta(days=1))

                logger.debug('[%r] 尝试买入: 股票[%s]，今日收盘[%.2f]，明日限价[%.2f]',
                             s_date,
                             self.data._name,
                             self.data.close[0],
                             limit_price)
        # 如果持仓
        else:
            if self.data.close[0] < self.ketler.lower[0]:
                logger.debug('[%r] 尝试卖出: 股票[%s]',
                             utils.date2str(self.data.datetime.datetime(0)), self.data._name)
                # 全部清仓
                self.order = self.close()

    def notify_order(self, order):

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
