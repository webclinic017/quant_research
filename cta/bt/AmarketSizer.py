import math

import backtrader as bt
import logging

from utils import utils
from utils.utils import calc_size

logger = logging.getLogger(__name__)


class AMarketSize(bt.Sizer):
    """
    写这个是因为，我买卖的信号是头天产生的，但是，第二天才真正交易（第二天的开盘价），
    所以，我不知道那时候的价格，所以要自定义个sizer，在未来（第二天），用那时候的价格，
    来计算到底可以买多少股，而且，A股是有手数的约束，即必须是100股的整数倍。

    卖无所谓，没有这个限制。

    https://blog.csdn.net/h00cker/article/details/123717292
    规模（sizer）
    还有一个交易的类是sizer，就是一次买卖操作的规模，也可称之为赌注大小。比如你看多一个股票，那么你准备下多大赌注？在股票交易中，通常的单位是手。一手多少股呢？国内通常是100股，港股也有几十的。一手大概是多少钱？不同股票不同，比如伯克希尔哈撒韦，一手就得几百万吧。但是注意Backtrader中，单位是股。
    自定义sizer并不复杂，步骤如下：
    首先继承backtrader.Sizer。通过这个类，可以访问执行买卖操作的到strategy和broker，然后可以获取相应信息决定size大小。通过broker我们可以获取如下信息：
    数据（也就是对应的资产）的头寸：self.strategy.getposition(data)。
    投资组合的市值：self.broker.getvalue()，也可以通过self.strategy.broker.getvalue()获取。
    还有一些信息通过如下函数的接口获取。
    重写_getsizing(self, comminfo, cash, data, isbuy)函数，这个函数接口入参信息如下：
    """

    def _getsizing(self, comminfo, cash, data, isbuy):
        """
        comminfo：就是佣金的实例，包含有关数据（资产）佣金的信息，并允许计算头寸价值、操作（买卖）成本、操作佣金等。
        cash：当前broker中的现金。
        data：操作的目标数据（对应资产）。
        isbuy：是买入操作（Ture）还是卖出操作（False）。
        :return:
        """
        date = utils.date2str(data.datetime.datetime(1))
        tomorrow_open = data.open[1] # 这里做了一个trick，用的是明日的开盘价，open[1]而不是open[0]
        today_close = data.close[0]
        commission_rate = comminfo.p.commission
        commission = commission_rate * cash
        if not isbuy: # 卖的话，瞎返回一个
            return -1
        else:
            # 如果买的话，用明日开盘价计算整手数，
            # 但是，需要和今日收盘价做一个比较，原因是backtrader创建订单的时候，是在今天，用的是今日的收盘价，
            # 如果他算出来，你的size*今日收盘价+佣金>现金的话，就会报Margin也就是资金不够的错误，
            # 按理说，他的逻辑是明日按照开盘价才挂单，不应该考虑今日收盘价，但是，我debug发现确实有这么一个限制
            # 所以，我增加一个逻辑，如果明日开盘价>今日收盘价计算出来的size，就用今日收盘价计算所得size，也就是，取小的
            size_tomorrow = calc_size(cash, tomorrow_open, commission_rate)
            size_today = calc_size(cash, today_close, commission_rate)
            if size_tomorrow>size_today:
                size = size_today
                price = today_close
            else:
                size = size_tomorrow
                price = tomorrow_open

        logger.debug("计算[%s]股数: 现金[%.1f],明日[%s]开盘价[%.2f],股数[%0.1f],佣金[%.1f]",
                     '买' if isbuy else '卖',
                     cash,
                     date,
                     price,
                     size,
                     commission)
        return size
