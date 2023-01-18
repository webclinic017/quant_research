import logging

from utils.utils import str2date

logger = logging.getLogger(__name__)


class BackTester():
    """
    回测核心类，类似于backtrader的cerebro
    """

    def __init__(self, broker, start_date, end_date, buy_day='tomorrow'):
        """

        :param amount: 投资金额
        :param periods: 投资期数
        :param buy_day today|tomorrow ，是当日成交，还是下一个交易日成交
        :return:
        """
        # 交易代理商
        self.broker = broker

        if type(start_date) == str: start_date = str2date(start_date)
        if type(end_date) == str: end_date = str2date(end_date)
        self.start_date = start_date
        self.end_date = end_date

        self.buy_day = buy_day

    def set_broker(self, b):
        self.broker = b

    def set_strategy(self, s):
        self.strategy = s

    def set_data(self, funds_dict: dict, df_baseline: dict):
        """
        data是一个dict，你爱搁啥就啥，
        虽然是一个字典，但是都要求有date一个字段，会按照这个日期字段对齐，并且设为索引
        """
        # 创建一个所有日期的容器
        self.dates = set()

        # 先把基准的日期装进去
        self.dates = self.dates.union(df_baseline.index.tolist())

        # 这一坨都是在遍历所有的基金数据，合并他们的日期，再排序，得到所有的日期，用于执行回测的日期 => self.dates
        for name, df_fund in funds_dict.items():
            # 把基金们的日期都合并到一个集合中，这个日期很重要，用于后续的遍历
            self.dates = self.dates.union(df_fund.index.tolist())

        # 保存重整后的数据
        self.df_baseline = df_baseline
        self.fund_dict = funds_dict

        # 对日期集合进行排序
        self.dates = sorted(self.dates)

        # 把数据传递给broker和策略
        self.strategy.set_data(self.fund_dict, self.df_baseline)
        self.broker.set_data(self.fund_dict, self.df_baseline)

    def run(self):
        """
        核心函数，就是运行每一天
        :return:
        """
        for i, today in enumerate(self.dates):

            # 防止提早启动回测，只在start_date才开始，到end_date就结束
            if today < self.start_date: continue
            if today > self.end_date: return

            # 触发当日的策略执行
            if i == len(self.dates) - 1: continue  # 防止越界
            # 是当天价来交易，还是以下一个交易日来交易
            trade_day = today if self.buy_day == 'today' else self.dates[i + 1]

            # 这里会产生买单和卖单
            self.strategy.next(today=today, trade_date=trade_day)

            # 触发交易代理的执行，这里才会真正的执行交易
            self.broker.run(today)

            # logger.debug("[%s]日的回测结束了...",date2str(today))
            # logger.debug("-"*80)
