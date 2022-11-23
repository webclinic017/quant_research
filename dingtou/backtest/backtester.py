from backtest.cash_distribution import CashDistribute


class BackTester():

    def __init__(self, broker):
        """

        :param amount: 投资金额
        :param periods: 投资期数
        :return:
        """
        # 交易代理商
        self.broker = broker

    def set_broker(self, b):
        self.broker = b

    def set_strategy(self, s):
        self.strategy = s

    def set_data(self, data: dict):
        """
        data是一个dict，你爱搁啥就啥，
        虽然是一个字典，但是都要求有date一个字段，会按照这个日期字段对齐，并且设为索引
        """
        self.dates = set()
        for name, _data in data.items():
            # 把所有的数据都设置成日期为索引：
            # 要求每个数据中，要么索引叫index，要么有一个列叫date（然后把他变成索引）
            assert "date" in _data.columns or _data.index.name == 'date', \
                f"数据[{name}]的dataframe未包含date列：{_data.columns}"

            # 如果date在列中，把他变成索引
            if "date" in _data.columns:
                _data.set_index("date", inplace=True)

            # 把日期都合并到一个集合中
            self.dates = self.dates.union(_data.index.tolist())

        # 保存重整后的数据
        self.data = data

        # 对日期集合进行排序
        self.dates = sorted(self.dates)

        # 把数据传递给broker和策略
        self.strategy.set_data(self.data)
        self.broker.set_data(self.data)

    def run(self):
        """
        核心函数，就是运行每一天
        :return:
        """
        for i, today in enumerate(self.dates):
            print(today)

            # 触发当日的策略执行
            if i == len(self.dates) - 1: continue  # 防止越界
            self.strategy.next(today=today, tomorrow=self.dates[i + 1])

            # 触发交易代理的执行
            self.broker.run(today)
