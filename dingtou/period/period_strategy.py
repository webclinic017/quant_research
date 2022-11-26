import numpy as np
import talib

from backtest.strategy import Strategy
from backtest.utils import get_value, fit



class PeriodStrategy(Strategy):
    """
    定投策略:
        这个和timing的区别是，那个靠均线下跌去投，而这个就是定期傻投，
        是为了做对比。
    """

    def __init__(self, broker, cash_distribute, sma_periods):
        super().__init__(broker, cash_distribute)
        self.sma_periods = sma_periods

    def set_data(self, df_baseline, funds_dict: dict):
        super().set_data(df_baseline, funds_dict)

        # 移动均线
        df_baseline['sma'] = talib.SMA(df_baseline.close, timeperiod=self.sma_periods)
        # 是否位于移动均线下方
        df_baseline['blow_sma'] = df_baseline.close < df_baseline.sma
        # 这3个，是用于判断是上涨，还是下跌，还是应该买入，分开是为了画图方便
        df_baseline['long'] = np.NaN
        df_baseline['short'] = np.NaN
        df_baseline['signal'] = np.NaN

    def next(self, today, next_trade_date):
        super().next(today, next_trade_date)

        df_baseline = self.df_baseline
        df_fund = list(self.funds_dict.values())[0]  # TODO: 这里先选择了第一只基金，将来多只的时候，要遍历的
        s_baseline = get_value(df_baseline, today)
        s_fund = get_value(df_fund, today)

        # 如果当天无指数数据，忽略，因为我们是根据指数的情况来决定买入的信号的
        if s_baseline is None: return

        # 获得指数收盘价
        baseline_close = None if s_baseline is None else s_baseline.close
        # 获得移动均线值
        flag_blow_sma = None if s_baseline is None else s_baseline.blow_sma
        # 获得均值
        sma_value = None if s_baseline is None else s_baseline.sma
        # 累计净值
        fund_code = None if s_fund is None else s_fund.code
        fund_net_value = None if s_fund is None else s_fund.close

        # print(f"{baseline_close},{fund_net_value},{flag_blow_sma}")

        df_last_4_index = df_baseline.iloc[df_baseline.index.get_loc(today) - 3:df_baseline.index.get_loc(today) + 1]

        if fund_code is None: return

        df_baseline.loc[today, 'signal'] = baseline_close  # 买信号
        # 计算出购入金额
        amount = self.cash_distribute.calculate(sma_value, current_value=baseline_close)
        # 扣除手续费后，下取整算购买份数
        self.broker.buy(fund_code, next_trade_date, amount)