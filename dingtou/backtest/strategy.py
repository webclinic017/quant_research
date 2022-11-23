import numpy as np
import talib

from backtest.utils import get_value, fit


class Strategy():

    def __init__(self, broker, cash_distribute):
        self.broker = broker
        # 资金分配策略
        self.cash_distribute = cash_distribute

    def set_data(self, d):
        self.data = d

    def next(self, today, tomorrow):
        """
        :param today: 当前的交易日
        :return:
        """
        print(f"策略日期:{today}")


class PeriodInvestStrategy(Strategy):
    """
    定投策略:

    资金分配策略：
        我有一笔钱，要定投到某个基金上，我给自己3~5年时间，也就是用3~5年把这笔钱投完，
        3~5年是参考了基金评价中的评价年限，当然我肯定会照着5年规划，防止中途弹药提前用完。

    """

    def __init__(self, broker, cash_distribute, sma_periods):
        super().__init__(broker, cash_distribute)
        self.sma_periods = sma_periods

    def set_data(self, data):
        super().set_data(data)
        df_index = data['index']
        df_index['sma'] = talib.SMA(df_index.close, timeperiod=self.sma_periods)
        df_index['blow_sma'] = df_index.close < df_index.sma
        df_index['long'] = np.NaN
        df_index['short'] = np.NaN
        df_index['signal'] = np.NaN

    def next(self, today, tomorrow):
        super().next(today, tomorrow)
        df_index = self.data['index']
        df_fund = self.data['fund']
        s_index = get_value(df_index, today)
        s_fund = get_value(df_fund, today)

        # 如果当天无指数数据，忽略
        if s_index is None: return

        # 获得指数收盘价
        index_close = None if s_index is None else s_index.close
        # 获得移动均线值
        flag_blow_sma = None if s_index is None else s_index.blow_sma
        # 获得均值
        sma_value = None if s_index is None else s_index.sma
        # 累计净值
        fund_code = None if s_fund is None else s_fund.code
        fund_net_value = None if s_fund is None else s_fund.value

        print(f"{index_close},{fund_net_value},{flag_blow_sma}")

        df_last_4_index = df_index.iloc[df_index.index.get_loc(today) - 3:df_index.index.get_loc(today) + 1]

        # 查看前4周的点的斜率，用一个拟合看斜率
        if not flag_blow_sma: return  # 如果是在均线之上就返回
        if len(df_last_4_index) < 4: return
        if fund_code is None: return

        # 如果在均线之下，如果斜率是正就是1，负就是-1
        y = df_last_4_index.close.to_numpy()
        x = [1, 2, 3, 4]
        k, b = fit(x, y)

        # 这个是为了保存涨跌买的数据，为了回溯和画图用
        if k > 0:  # 上涨
            df_index.loc[today, 'long'] = index_close  # 记录上涨
        else:  # 下跌
            index_pre_close = df_index.iloc[df_index.index.get_loc(today) - 1].close
            if index_close > index_pre_close:
                df_index.loc[today, 'short'] = index_close  # 仅记录下跌
            else:
                df_index.loc[today, 'signal'] = index_close  # 买信号
                # 计算出购入金额
                amount = self.cash_distribute.calculate(sma_value, current_value=index_close)
                # 扣除手续费后，下取整算购买份数
                self.broker.buy(fund_code, tomorrow, amount)
                # share = int(amount*(1-BUY_COMMISSION_RATE) / fund_net_value)
