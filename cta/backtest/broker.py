import logging

from pandas import DataFrame
import numpy as np
import math

from backtest.position import Position
from backtest.trade import Trade
from utils.utils import date2str, calc_size

logger = logging.getLogger(__name__)

# commission = 0.002  # 印花税 1‰(千1) + 过户费0.02‰(万0.2) + 券商交易佣金0.25‰(万2.5)
BUY_COMMISSION_RATE = 0.002  # 买入手续费1.5%
SELL_COMMISSION_RATE = 0.000  # 卖出手续费0.5%


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

    def __init__(self, cash, banker, is_A_share_market=True):
        """
        :param df_selected_stocks:
        :param df_daily:
        :param df_calendar:
        :param conservative:
        """
        # 这个banker是为了解决必须要可以持续有钱可以投入的情况，用于计算本金
        self.banker = banker
        self.total_cash = cash
        self.total_commission = 0
        self.is_A_share_market = is_A_share_market  # 是否是A股市场
        # self.total_buy_cash = 0  # 总投入资金：就是我每次投入到股市的资金的累计
        # self.total_sell_cash = 0  # 总收益资金：就是我每次卖出后的获利资金

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

    def set_data(self, fund_dict: dict, df_baseline:dict):
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
        if not trade.amount:  # 记录买卖金额
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

        price = series_fund.open # 要用开盘价来买入

        # 计算可以买多少股基金，是扣除了手续费的金额 / 基金当天净值，下取整
        if trade.position is None:
            assert trade.amount is not None
            position = int(trade.amount * (1 - self.buy_commission_rate) / price)
        else:
            position = trade.position

        # 如果卖出股数大于持仓，就只卖出所有持仓
        if position > self.positions[trade.code].position:
            logger.warning("[%s] 卖出基金[%s]股数%d>持仓%d，等同于清仓",
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

        logger.debug("[%s] [%s]以[%.2f]卖出[%.2f股/%.2f元],佣金[%.2f]",
                     date2str(date),
                     trade.code,
                     price,
                     position,
                     amount,
                     commission)

        # 计算卖出获得现金的时候，要刨除手续费
        self.cashin(date, amount - commission)

        # 创建，或者，更新持仓
        self.positions[trade.code].update(date, -position, price)
        if self.positions[trade.code] == 0:
            logger.info("基金[%s]仓位为0，清仓", trade.code)
            self.positions.pop(trade.ts_code, None)  # None可以防止pop异常

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
            # logger.debug("交易日期")
            return False

        # 先获得这笔交易对应的数据，也就是目标日的价格
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

        """
        # 先按照传入的事trade.amount 还是 trade.position，来算一个目标position出来
        """

        # 如果传入了trade.position
        if trade.position is not None:
            position = trade.position
        # 那么，就是传入了trade.amount
        else:
            # 如果是A股市场，要整数手
            if self.is_A_share_market:
                position = calc_size(trade.amount, series_fund.open, self.buy_commission_rate)
            else:
                position = int(trade.amount * (1 - self.buy_commission_rate) / series_fund.open)
        price = series_fund.open
        buy_value = position * price
        commission = self.buy_commission_rate * buy_value  # 还要算一下佣金，因为上面下取整了
        total_expense = buy_value + commission

        """
        # 然后，看现金够不够，如果不够，看能不能借入，如果不能借入，就重新调整买入仓位（使用剩余的全部现金）
        """

        # 如果是缺钱了就自动借入（银转证）的模式：
        if self.banker:
            # 计算实际需要的钱数，不够，就向银行借入
            if total_expense > self.total_cash:
                self.banker.credit(total_expense - self.total_cash)
                logger.warning("[%s] 购买基金[%s]金额不足，从银行借%.2f元",
                               date2str(today),
                               trade.code,
                               total_expense - self.total_cash)

        # 如果不提供从银行（银转证）随意转入的话，也就是，投资金额是完全固定死了，就需要重新计算买入仓位position
        else:
            if total_expense > self.total_cash:
                # 如果是A股市场，要整数手
                if self.is_A_share_market:
                    position = calc_size(self.total_cash, series_fund.open, self.buy_commission_rate)
                else:
                    position = int(self.total_cash * (1 - self.buy_commission_rate) / series_fund.open)
                buy_value = position * series_fund.open
                commission = self.buy_commission_rate * buy_value  # 还要算一下佣金，因为上面下取整了
                logger.warning("[%s] 购买[%s]，准备购买金额%.1f>现金%.2f，调整购买金额为%.1f,佣金%.1f,剩余现金%.1f",
                               date2str(today),
                               trade.code,
                               total_expense,
                               self.total_cash,
                               buy_value,
                               commission,
                               self.total_cash - buy_value - commission)

        # 买不到任何一个整数股数，就退出
        if position == 0:
            logger.warning("资金分配失败：从总现金[%.2f]中分配给基金[%s]（价格%.2f）失败",
                           self.total_cash, trade.code, series_fund.close)
            # 这笔交易就放弃了
            self.trades.remove(trade)
            return False

        """
        后续处理
        """

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

        logger.debug("[%s] 以[%.2f]价格买入[%s] %d股/%.2f元,佣金[%.2f],总持仓:%.0f股",
                     date2str(today),
                     price,
                     trade.code,
                     position,
                     buy_value,
                     commission,
                     self.positions[trade.code].position)

        # 现金流出：购买的价值 + 佣金，计算买入需要的现金的时候，要加上手续费
        self.cashout(today,total_expense)

        return True

    def cashin(self, date, amount):
        """
        卖出时候的现金增加
        :param amount:
        :return:
        """
        # 我的总现金量的变多了
        old_total_cash = self.total_cash
        self.total_cash += amount
        logger.debug("[%s] 总现金变化：%.2f+%.2f=>%.2f元，其中，总持仓：%.2f元，总市值：%.2f元",
                     date2str(date),
                     old_total_cash,
                     amount,
                     self.total_cash,
                     self.get_total_position_value(),
                     self.get_total_value())

    def cashout(self, date, amount):

        # 我的总资金量的变化
        old_total_cash = self.total_cash
        self.total_cash -= amount
        if self.total_cash<0:
            self.total_cash = 0 # 防止多减

        logger.debug("[%s] 总现金：%.2f-%.2f=>%.2f元，其中，总持仓：%.2f元，总市值：%.2f元",
                     date2str(date),
                     old_total_cash,
                     amount,
                     self.total_cash,
                     self.get_total_position_value(),
                     self.get_total_value())

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
        postion：购买股数
        这俩二选一
        """
        if amount and amount > self.total_cash and self.banker is None: # 如果不能从银行借钱
            logger.warning("创建%s日买入交易单失败：购买金额%.1f>持有现金%.1f", date2str(date), amount,
                           self.total_cash)
            return False
        self.trades.append(Trade(code, date, amount, position, 'buy'))
        logger.debug("创建目标交易日[%s]买单，买入[%s]，%r元 / %r股", date2str(date), code, amount, position)
        return True

    def sell(self, code, date, amount=None, position=None):
        """创建卖出单
        amount：购买金额
        postion：购买股数
        这俩二选一
        """
        if self.positions.get(code, None) is None:
            # logger.warning("[%s]创建卖单失败，[%s]不在仓位重", date2str(date), code)
            return False

        if self.positions[code].position == 0:
            logger.warning("[%s]创建卖单失败，[%s]仓位为0", date2str(date), code)
            return False

        if position and position > self.positions[code].position:
            logger.warning("[%s]卖出[%s]的仓位[%d]>持仓[%d]，清仓卖出",
                           date2str(date),
                           code,
                           position,
                           self.positions[code].position)
            # 超过仓位，就只卖出所有，清仓
            position = self.positions[code].position

        self.trades.append(Trade(code, date, amount, position, 'sell'))
        logger.debug("创建目标交易日[%s]卖单，卖出持仓基金 [%s] %r元/%r股",
                     date2str(date),
                     code,
                     amount,
                     position)
        return True

    def sell_out(self, code, date):
        """清仓单"""
        position = self.positions[code]
        return self.sell(code, date, position=position.position)

    def update_total_market_value(self, date):
        """
        更新你持有的组合的每日市值
        列：[日子，总市值，现金，市值]
        市值 = sum(position_i * price_i)
        总成本：
        每个基金成本 * 仓位权重
        """
        total_position_value = 0
        total_positions = []
        costs = []
        # 挨个持仓合计
        for fund_code, df_market_value in self.fund_market_dict.items():
            # 取最后一条，也就是最新的这只基金的各种信息
            # 这个信息已经在前面的update_market_value被更新，就是当天的、最新的
            total_position_value += df_market_value.iloc[-1].position_value.item()
            # 记录每只基金的最后总仓位
            total_positions.append(df_market_value.iloc[-1].position.item())
            # 记录每只基金的最后成本
            costs.append(df_market_value.iloc[-1].cost.item())

        # print("total_position_value========>",total_position_value)

        # 按照持仓股数，来计算平均成本
        total_position = sum(total_positions)
        if total_position == 0:
            cost = np.nan
        else:
            weights = [p / total_position for p in total_positions]
            cost = sum([c * w for c, w in zip(costs, weights)])

        # 更新记录
        self.df_total_market_value = self.df_total_market_value.append({
            'date': date,
            'total_value': total_position_value + self.total_cash,  # 总市值
            'total_position_value': total_position_value,  # 总持仓价值（不含现金）
            'cash': self.total_cash,
            'total_position': total_position,
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
            price = series_fund.close
            # logger.debug(" %s 日基金 %s 的数据，市值%.1f = 价格%.1f * 持仓%.1f ",
            #              date, code, market_value, series_fund.net_value, position.position)
        except KeyError:
            logger.warning(" %s 日没有基金 %s 的数据，使用其最后的市值未最新市值", date2str(date), fund_code)
            price = 0

        # 当前仓位（已经更新了今日的了）
        position = self.positions[fund_code].position

        # 更新当天市值
        if price==0:
            # 如果当天没有价格，就使用前一日的市场价值做为最新
            fund_position_value = self.fund_market_dict[fund_code].iloc[-1].position_value
        else:
            fund_position_value = self.positions[fund_code].position * price

        # 当前成本
        cost = self.positions[fund_code].cost
        # 这个是创建（也就是插入）一行到dataframe里，也就是组合的当日市值
        self.fund_market_dict[fund_code] = \
            df_fund_market_value.append({'date': date,
                                         'position_value': fund_position_value,  # 市值
                                         'position': position,  # 持仓
                                         'cost': cost}, ignore_index=True)  # 成本

    def get_total_value(self):
        """最新的总资产值:持仓+现金"""
        return self.df_total_market_value.iloc[-1].total_value

    def get_position_value(self, code):
        """仅查看某一直基金的持仓价值"""
        df_market_value = self.fund_market_dict.get(code, None)
        if df_market_value is None: return None
        return df_market_value.iloc[-1].position_value

    def get_total_position_value(self):
        """最新的总仓位值：仅持仓"""
        return self.df_total_market_value.iloc[-1].total_position_value

    def set_strategy(self, strategy):
        self.strategy = strategy

    def run(self, day_date):
        """
        这个定义，代理商每天要干啥
        day_date，今天的日期
        :return:
        """
        result = len(self.trades) > 0
        original_position_size = len(self.positions)

        # 先执行买入和卖出操作
        # bugfix:2023.1.9，很低级的一个错误，在list遍历的时候，删除元素导致bug，
        # 解决办法是，从后往前遍历，这样删除就不会导致遍历问题了
        # https://blog.csdn.net/cckavin/article/details/83618306
        # 倒序删除: 因为列表总是“向前移”，所以可以倒序遍历，即使后面的元素被修改了，还没有被遍历的元素和其坐标还是保持不变的。
        for i in range(len(self.trades)-1,-1,-1):
            trade = self.trades[i]
            if trade.action == 'sell':
                self.real_sell(trade, day_date)
            else:
                self.real_buy(trade, day_date)

        if original_position_size != len(self.positions):
            logger.debug("%s 日后，仓位变化，从%d=>%d 只",
                         date2str(day_date),
                         original_position_size,
                         len(self.positions))

        for code, _ in self.positions.items():
            # 更新市值，每天都要把当天的市值记录下来
            self.update_market_value(day_date, code)

        self.update_total_market_value(day_date)

        return result # 如果有交易，才返回True
