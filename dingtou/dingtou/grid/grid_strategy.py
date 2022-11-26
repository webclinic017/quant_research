import talib

from dingtou.backtest import utils
from dingtou.backtest.strategy import Strategy
from dingtou.backtest import fit


class GridStrategy(Strategy):
    """
    网格策略
    """

    def __init__(self, broker, cash_distribute, sma_periods):
        super().__init__(broker, cash_distribute)
        self.sma_periods = sma_periods

    def set_data(self, df_baseline, funds_dict: dict):
        super().set_data(df_baseline, funds_dict)

        for code, df_fund in funds_dict.items():

            # 把日数据变成周数据，并，生成周频的ATR
            df_fund = df_fund.rename(columns={'净值日期': 'date', '累计净值': 'close'})
            df_fund['high'] = df_fund.close
            df_fund['low'] = df_fund.close
            df_fund['open'] = df_fund.close
            df_week = utils.day2week(df_fund)
            df_week['atr'] = talib.ATR(df_week.high, df_week.low, df_week.close, timeperiod=20)
            funds_dict[code] = df_week


    def next(self, week_day, next_trade_date):
        super().next(week_day, next_trade_date)

        df_baseline = self.df_baseline
        df_fund = list(self.funds_dict.values())[0]  # TODO: 这里先选择了第一只基金，将来多只的时候，要遍历的

        # print(f"{index_close},{fund_net_value},{flag_blow_sma}")

        df_last_4_index = df_baseline.iloc[df_baseline.index.get_loc(today) - 3:df_baseline.index.get_loc(today) + 1]

        # 如果不是周线
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

                # 计算出购入金额
                amount, ratio = self.cash_distribute.calculate(sma_value, current_value=index_close)

                df_baseline.loc[today, 'signal'] = index_close * ratio  # 买信号

                # 扣除手续费后，下取整算购买份数
                self.broker.buy(fund_code, next_trade_date, amount)
                # share = int(amount*(1-BUY_COMMISSION_RATE) / fund_net_value)
