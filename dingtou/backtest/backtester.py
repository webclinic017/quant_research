from datetime import datetime


class BackTester():

    def __init__(self, broker, start_date, end_date):
        """

        :param amount: 投资金额
        :param periods: 投资期数
        :return:
        """
        # 交易代理商
        self.broker = broker
        self.start_date = start_date
        self.end_date = end_date

    def set_broker(self, b):
        self.broker = b

    def set_strategy(self, s):
        self.strategy = s

    def set_data(self, df_baseline, funds_dict: dict):
        """
        data是一个dict，你爱搁啥就啥，
        虽然是一个字典，但是都要求有date一个字段，会按照这个日期字段对齐，并且设为索引
        """
        # 创建一个所有日期的容器
        self.dates = set()

        # 先把基准的日期装进去
        self.dates = self.dates.union(df_baseline.index.tolist())

        for name, df_fund in funds_dict.items():
            # 把所有的数据（基准baseline和所有的基金）都设置成日期为索引：
            # 要求每个数据中，要么索引叫index，要么有一个列叫date（然后把他变成索引）
            assert "date" in df_fund.columns or df_fund.index.name == 'date', \
                f"数据[{name}]的dataframe未包含date列：{df_fund.columns}"

            # 如果date在列中，把他变成索引
            if "date" in df_fund.columns:
                df_fund.set_index("date", inplace=True)

            # 把基金们的日期都合并到一个集合中，这个日期很重要，用于后续的遍历
            self.dates = self.dates.union(df_fund.index.tolist())

        # 保存重整后的数据
        self.df_baseline = df_baseline
        self.fund_dict = funds_dict

        # 对日期集合进行排序
        self.dates = sorted(self.dates)

        # 把数据传递给broker和策略
        self.strategy.set_data(self.df_baseline, self.fund_dict)
        self.broker.set_data(self.df_baseline, self.fund_dict)

    def run(self):
        """
        核心函数，就是运行每一天
        :return:
        """
        for i, today in enumerate(self.dates):
            if today < datetime.strptime(self.start_date, "%Y%m%d"): continue
            if today > datetime.strptime(self.end_date, "%Y%m%d"): return

            # 触发当日的策略执行
            if i == len(self.dates) - 1: continue  # 防止越界
            self.strategy.next(today=today, next_trade_date=self.dates[i + 1])

            # 触发交易代理的执行
            self.broker.run(today)
