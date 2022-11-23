import numpy as np
import talib

from backtest.utils import get_value, fit


class Strategy():

    def __init__(self, broker, cash_distribute):
        self.broker = broker
        # 资金分配策略
        self.cash_distribute = cash_distribute

    def set_data(self, df_baseline, funds_dict: dict):
        self.df_baseline = df_baseline
        self.funds_dict = funds_dict

    def next(self, today, next_trade_date):
        """
        :param today: 当前的交易日
        :return:
        """
        # print(f"策略日期:{today}")


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

    def set_data(self, df_baseline, funds_dict: dict):
        super().set_data(df_baseline, funds_dict)
        df_baseline['sma'] = talib.SMA(df_baseline.close, timeperiod=self.sma_periods)
        df_baseline['blow_sma'] = df_baseline.close < df_baseline.sma
        df_baseline['long'] = np.NaN
        df_baseline['short'] = np.NaN
        df_baseline['signal'] = np.NaN

    def next(self, today, next_trade_date):
        super().next(today, next_trade_date)

        df_baseline = self.df_baseline
        df_fund = list(self.funds_dict.values())[0]  # TODO: 这里先选择了第一只基金，将来多只的时候，要遍历的
        s_index = get_value(df_baseline, today)
        s_fund = get_value(df_fund, today)

        # 如果当天无指数数据，忽略，因为我们是根据指数的情况来决定买入的信号的
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

        # print(f"{index_close},{fund_net_value},{flag_blow_sma}")

        df_last_4_index = df_baseline.iloc[df_baseline.index.get_loc(today) - 3:df_baseline.index.get_loc(today) + 1]

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
            df_baseline.loc[today, 'long'] = index_close  # 记录上涨
        else:  # 下跌
            index_pre_close = df_baseline.iloc[df_baseline.index.get_loc(today) - 1].close
            if index_close > index_pre_close:
                df_baseline.loc[today, 'short'] = index_close  # 仅记录下跌
            else:
                df_baseline.loc[today, 'signal'] = index_close  # 买信号
                # 计算出购入金额
                amount = self.cash_distribute.calculate(sma_value, current_value=index_close)
                # 扣除手续费后，下取整算购买份数
                self.broker.buy(fund_code, next_trade_date, amount)
                # share = int(amount*(1-BUY_COMMISSION_RATE) / fund_net_value)
