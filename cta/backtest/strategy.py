import numpy as np


class Strategy():
    """
    策略类的父类
    """

    def __init__(self, broker, cash_distribute):
        self.broker = broker
        # 资金分配策略
        self.cash_distribute = cash_distribute

    def get_position(self,code):
        return self.broker.positions.get(code,None)

    def set_data(self, df_baseline, df_dict: dict):
        self.df_baseline = df_baseline
        self.df_dict = df_dict

    def get_value(self, df, key):
        try:
            return df.loc[key]
        except KeyError:
            return None

    def next(self, today, trade_date):
        """
        :param today: 当前的交易日
        :return:
        """
        # print(f"策略日期:{today}")