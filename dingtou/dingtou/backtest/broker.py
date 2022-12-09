import logging

from pandas import DataFrame
import numpy as np

from dingtou.backtest.position import Position
from dingtou.backtest.trade import Trade
from research.utils import date2str

logger = logging.getLogger(__name__)

BUY_COMMISSION_RATE = 0.015  # 买入手续费1.5%
SELL_COMMISSION_RATE = 0.005  # 卖出手续费0.5%


def next_trade_day(date, df_calendar):
    """
    下一个交易日
    :return:
    """
    index = df_calendar[df_calendar == date].index[0] + 1
    if index > len(df_calendar): return None
    return df_calendar[index]


class Broker:
    """
    实现一个代理商broker的功能
    每天运行买卖就行

    有几个概念：
    - 总资金：比如说是50万，但是我不一定都投到股市里
    - 总投入资金：就是我每次投入到股市的资金的累计
    - 总收益资金：就是我每次卖出后的获利资金
    - 持仓：就是我某只股票的仓位
    """

    def __init__(self, cash):
        """
        :param df_selected_stocks:
        :param df_daily:
        :param df_calendar:
        :param conservative:
        """
        self.total_cash = cash
        self.total_commission = 0
        self.total_buy_cash = 0  # 总投入资金：就是我每次投入到股市的资金的累计
        self.total_sell_cash = 0  # 总收益资金：就是我每次卖出后的获利资金

        self.buy_commission_rate = BUY_COMMISSION_RATE  # 买入默认的手续费
        self.sell_commission_rate = SELL_COMMISSION_RATE  # 卖出默认的手续费

        # 存储数据的结构
        self.positions = {}
        # 保存发起的交易：买单交易、买单交易
        self.trades = []
        # 记录完成的交易，就似乎把发起的交易成功后，转移到这里
        self.df_trade_history = DataFrame()
        # 总持仓的每日市值
        self.df_total_market_value = DataFrame()
        # 各个基金的每日市值
        self.fund_market_dict = {}

    def set_buy_commission_rate(self, commission_rate):
        self.buy_commission_rate = commission_rate

    def set_sell_commission_rate(self, commission_rate):
        self.sell_commission_rate = commission_rate

    def set_data(self, df_baseline, fund_dict: dict):
        # 基金数据，是一个dict，key是基金代码，value是dataframe
        self.fund_dict = fund_dict
        # 基准指数
        self.df_baseline = df_baseline
        date = list(self.fund_dict.values())[0].iloc[0]._name
        self.df_total_market_value = self.df_total_market_value.append({'date': date,
                                                                          'total_value': self.total_cash,  # 总市值
                                                                          'total_position_value': 0,
                                                                        # 总持仓价值（不含现金）
                                                                          'cash': self.total_cash},
                                                                       ignore_index=True)

    def add_trade_history(self, trade, today, price):
        trade.actual_date = today
        trade.price = price
        if not trade.amount: # 记录买卖金额
            trade.amount = trade.position * trade.price
        self.df_trade_history = self.df_trade_history.append(trade.to_dict(), ignore_index=True)

    def real_sell(self, trade, date):
        # 先获得这笔交易对应的数据
        try:
            # 使用try/exception + 索引loc是为了提速，直接用列，或者防止KeyError的intersection，都非常慢， 60ms vs 3ms，20倍关系
            # 另外，date列是否是str还是date/int对速度影响不大
            # df_stock = self.df_daily.loc[self.df_daily.index.intersection([(date, trade.code)])]
            df = self.fund_dict[trade.code]
            series_fund = df.loc[trade.target_date]
        except KeyError:
            logger.warning("基金[%s]没有在[%s]无数据，无法买入，只能延后", trade.code, date)
            return False

        price = series_fund.net_value

        # 计算可以买多少份基金，是扣除了手续费的金额 / 基金当天净值，下取整
        if trade.position is None:
            assert trade.amount is not None
            position = int(trade.amount * (1 - self.buy_commission_rate) / price)
        else:
            position = trade.position

        # 如果卖出份数大于持仓，就只卖出所有持仓
        if position > self.positions[trade.code].position:
            logger.warning("[%s]卖出基金[%s]份数%d>持仓%d，等同于清仓",
                           date2str(date),
                           trade.code,
                           position,
                           self.positions[trade.code].position)
            position = self.positions[trade.code].position

        # 计算佣金
        amount = price * position
        commission = amount * SELL_COMMISSION_RATE
        self.total_commission += commission

        # 更新头寸,仓位,交易历史
        self.trades.remove(trade)
        self.add_trade_history(trade, date, price)
        # 计算卖出获得现金的时候，要刨除手续费
        self.cashin(amount - commission)

        # 创建，或者，更新持仓
        self.positions[trade.code].update(date, -position, price)
        if self.positions[trade.code] == 0:
            logger.info("基金[%s]仓位为0，清仓", trade.code)
            self.positions.pop(trade.ts_code, None)  # None可以防止pop异常

        logger.debug("[%s]于[%s]以[%.2f]卖出[%.2f份/%.2f元],佣金[%.2f]",
                     trade.code,
                     date2str(date),
                     price,
                     position,
                     amount,
                     commission)
        return True

    def real_buy(self, trade, today):
        """
        真正的去买
        :param trade:
        :param today:
        :return:
        """
        # 如果今天还没到买单的日期，就退出这个trade的交易
        if trade.target_date > today:
            return False

        # 先获得这笔交易对应的数据
        try:
            # 使用try/exception + 索引loc是为了提速，直接用列，或者防止KeyError的intersection，都非常慢， 60ms vs 3ms，20倍关系
            # 另外，date列是否是str还是date/int对速度影响不大
            # df_stock = self.df_daily.loc[self.df_daily.index.intersection([(date, trade.code)])]
            df = self.fund_dict[trade.code]
            series_fund = df.loc[trade.target_date]
        except KeyError:
            logger.warning("基金[%s]没有在[%s]无数据，无法买入，只能延后", trade.code, today)
            return False

        # assert len(df_stock) == 1, f"根据{date}和{trade.code}筛选出多于1行的数据：{len(df_stock)}行"

        # 计算可以买多少份基金，是扣除了手续费的金额 / 基金当天净值，下取整
        if trade.position is None:
            assert trade.amount is not None
            position = int(trade.amount * (1 - self.sell_commission_rate) / series_fund.net_value)
        else:
            position = trade.position

        # 计算要购买的价值（市值）
        price = series_fund.net_value
        buy_value = position * price
        commission = self.buy_commission_rate * buy_value  # 还要算一下佣金，因为上面下取整了

        # 现金不够这次交易了，就退出
        if buy_value + commission > self.total_cash:
            import math
            original_buy =  buy_value + commission
            available_money = self.total_cash/(self.buy_commission_rate+1)
            position = available_money/price
            position = math.floor(position)
            buy_value = position*price
            commission = self.buy_commission_rate * buy_value  # 还要算一下佣金，因为上面下取整了
            logger.warning("[%s]购买基金[%s]，购买金额%.1f>现金%.0f，调整购买金额为%.1f,佣金%.1f,剩余现金%.1f",
                           date2str(today),
                           trade.code,
                           original_buy,
                           self.total_cash,
                           buy_value,
                           commission,
                           self.total_cash - buy_value - commission)

        # 买不到任何一个整数份数，就退出
        if position == 0:
            logger.warning("资金分配失败：从总现金[%.2f]中分配给基金[%s]（价格%.2f）失败",
                           self.total_cash, trade.code, series_fund.net_value)
            return False

        # 记录累计佣金
        self.total_commission += commission

        # 更新仓位,头寸,交易历史
        self.trades.remove(trade)
        self.add_trade_history(trade, today, price)

        # 创建，或者，更新持仓
        if trade.code in self.positions:
            self.positions[trade.code].update(today, position, price)
        else:
            self.positions[trade.code] = Position(trade.code, position, price, today)

        # 一种现金流出：购买的价值 + 佣金，计算买入需要的现金的时候，要加上手续费
        self.cashout(buy_value + commission)

        logger.debug("%s以[%.2f]价格买入[%s] %d份/%.2f元,佣金[%.2f],总持仓:%.0f份",
                     date2str(today),
                     price,
                     trade.code,
                     position,
                     buy_value,
                     commission,
                     self.positions[trade.code].position)
        return True

    def cashin(self, amount):
        """
        卖出时候的现金增加
        :param amount:
        :return:
        """
        # 我的总现金量的变多了
        old_total_cash = self.total_cash
        self.total_cash += amount
        logger.debug("我的总现金增加：%2.f=>%.2f", old_total_cash, self.total_cash)

        # 我从股市上获利了结的总资金量增加了
        old_total_sell_cash = self.total_sell_cash
        self.total_sell_cash += amount
        logger.debug("投入股市总现金：%2.f=>%.2f", old_total_sell_cash, self.total_sell_cash)

        # 我的持仓市值的增加变化
        logger.debug("我持有市值变为：%2.f元", self.get_total_position_value())

    def cashout(self, amount):

        # 我的总资金量的变化
        old_total_cash = self.total_cash
        self.total_cash -= amount
        logger.debug("我的总现金减少：%2.f=>%.2f", old_total_cash, self.total_cash)

        # 我从股市上获利了结的总资金量增加的变化
        old_total_buy_cash = self.total_buy_cash
        self.total_buy_cash += amount
        logger.debug("投入股市总现金：%2.f=>%.2f", old_total_buy_cash, self.total_buy_cash)

        # 我的持仓市值的增加变化
        logger.debug("我持有市值变为：%2.f元", self.get_total_position_value())

    def is_in_position(self, code):
        for position_code, _ in self.positions.items():
            if position_code == code: return True
        return False

    def clear_buy_trades(self):
        self.trades = [t for t in self.trades if t.action == 'sell']

    def is_in_sell_trades(self, code):
        for t in self.trades:
            if t.action != 'sell': continue
            if t.code == code: return True
        return False

    def get_buy_trade_num(self):
        return len([t for t in self.trades if t.action == 'buy'])

    def buy(self, code, date, amount=None, position=None):
        """
        创建买入单，下个交易日成交
        amount：购买金额
        postion：购买份数
        这俩二选一
        """
        if amount and amount > self.total_cash:
            logger.warning("创建%s日买入交易单失败：购买金额%.1f>持有现金%.1f", date2str(date), amount,
                           self.total_cash)
            return False
        self.trades.append(Trade(code, date, amount, position, 'buy'))
        logger.debug("[%s]创建买单，买入基金[%s]%r元/%r份", date2str(date), code, amount, position)
        return True

    def sell(self, code, date, amount=None, position=None):
        """创建卖出单
        amount：购买金额
        postion：购买份数
        这俩二选一
        """
        if self.positions.get(code, None) is None:
            # logger.warning("[%s]创建卖单失败，[%s]不在仓位重", date2str(date), code)
            return False

        if self.positions[code].position == 0:
            # logger.warning("[%s]创建卖单失败，[%s]仓位为0",date2str(date),code)
            return False

        if position and position > self.positions[code].position:
            logger.warning("[%s]卖出[%s]的仓位[%d]>持仓[%d]",
                           date2str(date),
                           code,
                           position,
                           self.positions[code].position)
            # 超过仓位，就只卖出所有，清仓
            position = self.positions[code].position

        self.trades.append(Trade(code, date, amount, position, 'sell'))
        logger.debug("创建下个交易日[%s]卖单，卖出持仓基金 [%s] %r元/%r份", date2str(date), code, amount,
                     position)
        return True

    def sell_out(self, code, date):
        """清仓单"""
        position = self.positions[code]
        self.sell(code, date, position=position.position)

    def update_total_market_value(self, date):
        """
        更新你持有的组合的每日市值
        列：[日子，总市值，现金，市值]
        市值 = sum(position_i * price_i)
        总成本：
        每个基金成本 * 仓位权重
        """
        market_value = 0
        positions = []
        costs = []
        # 挨个持仓合计
        for fund_code, df_market_value in self.fund_market_dict.items():
            # 取最后一条，也就是最新的这只基金的各种信息
            # 这个信息已经在前面的update_market_value被更新，就是当天的、最新的
            market_value += df_market_value.iloc[-1].market_value.item()
            positions.append(df_market_value.iloc[-1].position.item())
            costs.append(df_market_value.iloc[-1].cost.item())
        total_position = sum(positions)
        if total_position==0:
            cost = np.nan
        else:
            weights = [p / total_position for p in positions]
            cost = sum([c * w for c, w in zip(costs, weights)])
        self.df_total_market_value = self.df_total_market_value.append({'date': date,
                                                'total_value': market_value + self.total_cash,  # 总市值
                                                'market_value': market_value,  # 总持仓价值（不含现金）
                                                'cash': self.total_cash,
                                                'cost': cost}, ignore_index=True)

    def update_market_value(self, date, fund_code):
        """
        更新你持有的基金的每日市值
        列：[日子，仓位，市值，成本]
        """
        total_position_value = 0
        total_cost = 0

        # 找到这只基金的当天的价格，然后乘以仓位，计算这笔成交的市值
        df_fund_daily = self.fund_dict[fund_code]

        # 找到基金每日持仓市值，准备更新他
        df_fund_market_value = self.fund_market_dict.get(fund_code, None)
        if df_fund_market_value is None:
            df_fund_market_value = DataFrame()

        # 获得此基金的当日价格
        try:
            series_fund = df_fund_daily.loc[date]
            price = series_fund.net_value
            # logger.debug(" %s 日基金 %s 的数据，市值%.1f = 价格%.1f * 持仓%.1f ",
            #              date, code, market_value, series_fund.net_value, position.position)
        except KeyError:
            logger.warning(" %s 日没有基金 %s 的数据，当天它的市值计作 0 ", date, fund_code)
            price = 0

        # 当前仓位（已经更新了今日的了）
        position = self.positions[fund_code].position

        # 当前市值
        fund_market_value = self.positions[fund_code].position * price

        # 当前成本
        cost = self.positions[fund_code].cost
        # 这个是创建（也就是插入）一行到dataframe里，也就是组合的当日市值
        self.fund_market_dict[fund_code] = \
            df_fund_market_value.append({'date': date,
                                         'market_value': fund_market_value,  # 市值
                                         'position': position,  # 持仓
                                         'cost': cost}, ignore_index=True)  # 成本

    def get_total_value(self):
        """最新的总资产值:持仓+现金"""
        return self.df_total_market_value.iloc[-1].total_value

    def get_position_value(self, code):
        """仅查看某一直基金的持仓价值"""
        df_fund_mareket_value = self.fund_market_dict.get(code, None)
        if df_fund_mareket_value is None: return None
        return df_fund_mareket_value.iloc[-1].market_value

    def get_total_position_value(self):
        """最新的总仓位值：仅持仓"""
        return self.df_total_market_value.iloc[-1].market_value


    def set_strategy(self, strategy):
        self.strategy = strategy

    def run(self, day_date):
        """
        这个定义，代理商每天要干啥
        day_date，今天的日期
        :return:
        """
        original_position_size = len(self.positions)

        # 先执行卖出操作
        sell_trades = [x for x in self.trades if x.action == 'sell']
        for trade in sell_trades:
            if self.real_sell(trade, day_date):
                # 更新市值，每天都要把当天的市值记录下来
                self.update_market_value(day_date, trade.code)

        # 再执行买入操作
        buy_trades = [x for x in self.trades if x.action == 'buy']
        for trade in buy_trades:
            if self.real_buy(trade, day_date):
                # 更新市值，每天都要把当天的市值记录下来
                self.update_market_value(day_date, trade.code)

        if original_position_size != len(self.positions):
            logger.debug("%s 日后，仓位变化，从%d=>%d 只", date2str(day_date), original_position_size,
                         len(self.positions))

        self.update_total_market_value(day_date)
