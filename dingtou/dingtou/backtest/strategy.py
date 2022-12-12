import numpy as np


class Strategy():
    """
    策略类的父类
    """

    def __init__(self, broker, cash_distribute):
        self.broker = broker
        # 资金分配策略
        self.cash_distribute = cash_distribute

    def set_data(self, df_baseline, funds_dict: dict):
        self.df_baseline = df_baseline
        self.funds_dict = funds_dict

    def next(self, today, trade_date):
        """
        :param today: 当前的交易日
        :return:
        """
        # print(f"策略日期:{today}")