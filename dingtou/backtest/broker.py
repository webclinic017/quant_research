import logging
import math

from pandas import DataFrame

logger = logging.getLogger(__name__)

BUY_COMMISSION_RATE = 0.015  # 买入手续费1.5%
SELL_COMMISSION_RATE = 0.005  # 卖出手续费0.5%


def next_trade_day(trade_date, df_calendar):
    """
    下一个交易日
    :return:
    """
    index = df_calendar[df_calendar == trade_date].index[0] + 1
    if index > len(df_calendar): return None
    return df_calendar[index]


class Trade:
    """
    用来定义一个交易
    """

    def __init__(self, code, target_date, amount, action):
        self.code = code
        self.target_date = target_date
        self.action = action
        self.actual_date = None
        self.amount = amount


class Position:
    """
    用来定义持有的仓位
    """

    def __init__(self, code, position, create_date, initial_value):
        self.code = code
        self.position = position
        self.create_date = create_date
        self.initial_value = initial_value


class Broker:
    """
    实现一个代理商broker的功能
    每天运行买卖就行
    """

    def __init__(self,cash):
        """
        :param df_selected_stocks:
        :param df_daily:
        :param df_calendar:
        :param conservative:
        """
        self.cash = cash
        self.total_commission = 0

        # 存储数据的结构
        self.positions = {}
        self.trades = []
        self.df_values = DataFrame()

    def set_data(self, data):
        # 投资的标的
        # self.df_daily = df_daily.set_index(['date', 'code'])  # 设索引是为了加速，太慢了否则
        # self.df_index = df_index
        # self.df_calendar = df_calendar
        # self.daily_trade_dates = df_daily.trade_date.unique()
        self.data = data

    def real_sell(self, trade, trade_date):
        try:
            df_stock = self.df_daily.loc[(trade_date, trade.code)]
        except KeyError:
            logger.warning("基金[%s]没有在[%s]无数据，无法卖出，只能延后", trade.code, trade_date)
            return False

        # assert len(df_stock) == 1, f"根据{trade_date}和{trade.code}筛选出多于1行的数据：{len(df_stock)}行"

        position = self.positions[trade.code]
        amount = price * position.position
        commission = amount * SELL_COMMISSION_RATE
        self.total_commission += commission

        # 更新头寸,仓位,交易历史
        self.trades.remove(trade)
        self.cashin(amount - commission)
        self.positions.pop(trade.code, None)  # None可以防止pop异常
        _return = (amount - position.initial_value) / position.initial_value

        trade.trade_date = trade_date

        logger.debug("[%s]于[%s]以[%.2f]卖出,买入=>卖出[%.2f=>%.2f],佣金[%.2f],收益[%.1f%%]",
                     trade.code, trade_date, price, position.initial_value, amount, commission, _return * 100)
        return True

    def real_buy(self, trade, trade_date):
        # 使用try/exception + 索引loc是为了提速，直接用列，或者防止KeyError的intersection，都非常慢， 60ms vs 3ms，20倍关系
        # 另外，trade_date列是否是str还是date/int对速度影响不大
        # df_stock = self.df_daily.loc[self.df_daily.index.intersection([(trade_date, trade.code)])]
        df = self.data['fund']
        try:
            series_fund = df.loc[trade.target_date]
        except KeyError:
            logger.warning("基金[%s]没有在[%s]无数据，无法买入，只能延后", trade.code, trade_date)
            return False

        # assert len(df_stock) == 1, f"根据{trade_date}和{trade.code}筛选出多于1行的数据：{len(df_stock)}行"

        price = series_fund.value

        # 计算可以买多少份基金，是扣除了手续费的金额 / 基金当天净值
        position = int(trade.amount * (1 - BUY_COMMISSION_RATE) / series_fund.value)

        if position == 0:
            logger.warning("资金分配失败：从总现金[%.2f]中分配给基金[%s]（价格%.2f）失败",
                           self.cash, trade.code, price)
            return False

        # 计算实际费用
        actual_cost = position * price
        # 计算佣金
        commission = BUY_COMMISSION_RATE * actual_cost
        self.total_commission += commission

        # 更新仓位,头寸,交易历史
        self.trades.remove(trade)
        self.positions[trade.code] = Position(trade.code, position, trade_date, actual_cost)
        self.cashout(actual_cost + commission)

        logger.debug("基金[%s]已于[%s]日按照最高价[%.2f]买入%d股,买入金额[%.2f],佣金[%.2f]",
                     trade.code, trade_date, price, position, actual_cost, commission)
        return True

    def cashin(self, amount):
        old = self.cash
        self.cash += amount
        logger.debug("现金增加：%2.f=>%.2f", old, self.cash)

    def cashout(self, amount):
        old = self.cash
        self.cash -= amount
        logger.debug("现金减少：%2.f=>%.2f", old, self.cash)

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

    def buy(self, code, date, amount):
        """创建买入单，下个交易日成交"""
        self.trades.append(Trade(code, date, amount, 'buy'))
        logger.debug("创建下个交易日[%s]买单，买入基金 [%s] %.2f股", date, code, amount)

    def sell(self, code, date, amount):
        """创建卖出单"""
        self.trades.append(Trade(code, date, amount, 'sell'))
        logger.debug("创建下个交易日[%s]卖单，卖出持仓基金 [%s] %.2f股", date, code, amount)

    def update_market_value(self, trade_date):
        """
        # 日子，总市值，现金，市值
        市值 = sum(position_i * price_i)
        """
        total_position_value = 0
        for code, position in self.positions.items():
            # logger.debug("查找基金[%s] %s数据", code, trade_date)

            df = self.data['fund']
            try:
                series_fund = df.loc[trade_date]
                # assert len(df_the_stock) == 1, f"根据{trade_date}和{code}筛选出多于1行的数据：{len(df_the_stock)}行"
                market_value = series_fund.value * position.position
            except KeyError:
                logger.warning(" %s 日没有基金 %s 的数据，当天它的市值计作 0 ", trade_date, code)
                market_value = 0

            total_position_value += market_value

        total_value = total_position_value + self.cash
        self.df_values = self.df_values.append({'trade_date': trade_date,
                                                'total_value': total_value,
                                                'total_position_value': total_position_value,
                                                'cash': self.cash}, ignore_index=True)
        logger.debug("%s 市值 %.2f = %d只基金市值 %.2f + 持有现金 %.2f",
                     trade_date, total_value, len(self.positions), total_position_value, self.cash)

    def set_strategy(self, strategy):
        self.strategy = strategy

    def run(self, day_date):
        """
        这个定义，代理商每天要干啥
        day_date，今天的日期
        :return:
        """
        original_position_size = len(self.positions)

        # 先卖
        sell_trades = [x for x in self.trades if x.action == 'sell']
        for trade in sell_trades:
            self.real_sell(trade, day_date)

        # 后买
        buy_trades = [x for x in self.trades if x.action == 'buy']
        for trade in buy_trades:
            self.real_buy(trade, day_date)

        if original_position_size != len(self.positions):
            logger.debug("%s 日后，仓位变化，从%d=>%d 只", day_date, original_position_size, len(self.positions))

        # 更新市值，每天都要把当天的市值记录下来
        self.update_market_value(day_date)
