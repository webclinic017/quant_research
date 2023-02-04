import logging
import os.path

import pandas as pd
import numpy as np
from backtest.strategy import Strategy
from utils import data_loader
from utils.data_loader import set_date_index
from utils.utils import date2str, OLS

logger = logging.getLogger(__name__)


class TripleStrategy(Strategy):

    def __init__(self, broker, params):
        super().__init__(broker, None)
        self.params = params

    def set_data(self, df_dict: dict, df_baseline=None):
        super().set_data(df_baseline, df_dict)

        """
        1. 计算布林通道。
        
        https://tushare.pro/document/2?doc_id=47
        north_money	float	北向资金（百万元）
        south_money	float	南向资金（百万元）
        
        中轨线 = 90日的移动平均线（SMA)
        上轨线 = 90日的SMA +（90日的标准差 x 2）
        下轨线 = 90日的SMA -（90日的标准差 x 2）
        """
        df_flow = df_dict['moneyflow']
        df_flow['net_amount'] = df_flow.north_money - df_flow.south_money
        # 不能用talib，因为中间有一些na，会导致它全都变成na了，用dataframe.rolling替代
        # df_flow['_mid'] = talib.SMA(df_flow.net_amount, timeperiod=self.params.bolling_period)
        df_flow['_mid'] = df_flow.net_amount.rolling(window=self.params.bolling_period, min_periods=1).mean()
        # df_flow['_std'] = talib.STDDEV(df_flow.net_amount, timeperiod=self.params.bolling_period, nbdev=1)
        df_flow['_std'] = df_flow.net_amount.rolling(window=self.params.bolling_period, min_periods=1).std()

        df_flow['upper'] = df_flow._mid + self.params.bolling_std * df_flow._std
        df_flow['lower'] = df_flow._mid - self.params.bolling_std * df_flow._std
        self.df_flow = df_flow

        self.df_top10 = df_dict['top10']

    def next(self, today, trade_date):
        super().next(today, trade_date)

        s_flow = self.get_value(self.df_flow, index_key=today)
        if s_flow is None: return

        net_amount = s_flow.net_amount
        upper = s_flow.upper
        lower = s_flow.lower

        # logger.debug("指标：净值[%.1f],上轨[%.1f],下轨[%.1f]",net_amount,upper,lower)

        # 根据北上资金的净流入的布林通道开仓
        if net_amount > upper:
            logger.debug('[%s] 北上资金流出净值[%.1f] > 布林上轨[%.1f]，开仓：', date2str(today), net_amount, upper)

            # 获得今日的10大净流入股票，因为有沪市top10+深市top10，所有有20只
            df_today_stocks = self.get_value(self.df_top10, today)
            if df_today_stocks is None:
                logger.warning('今日[%s]没有流入股票', date2str(today))
                return
            # 按照净值流入从大到小排列（原作者是按照买入股份数，我没这个数据，用净流入资金更实在）
            df_today_stocks = df_today_stocks.sort_values(by='net_amount', ascending=False)
            df_today_stocks = df_today_stocks.iloc[self.params.top10_scope[0]:self.params.top10_scope[1]]

            # https://tushare.pro/document/2?doc_id=48
            for _, s_stock in df_today_stocks.iterrows():
                code = s_stock.code

                df = self.calculte_stock_rsrs(code)
                # 需要动态把这只股票加入到broker中
                self.broker.add_data(code,df)

                # 如果这只股票已经在持仓中
                if code in self.broker.positions.keys():
                    logger.debug("[%s] 已经在持仓中，检查是否需要卖出", code)
                    if zscore < - self.params.S:
                        logger.debug("[%s] 持仓中，zsocre < -S [%.1f/%1.f]，清仓！", code, zscore, - self.params.S)
                        self.broker.sell_out(code, trade_date)
                        logger.debug('[%r] 挂买单，股票[%s]/目标日期[%s]', date2str(today), code, date2str(trade_date))
                    else:
                        logger.debug("[%s] 持仓中，zsocre > -S [%.1f/%1.f]，继续持有", code, zscore, - self.params.S)
                else:
                    # 获得今日这只股票的调整后的zscore
                    zscore = self.get_value(df, today, 'adjust_zscore')
                    if zscore > self.params.S:
                        self.broker.buy(code, trade_date, amount=self.params.per_amount)
                        logger.debug('[%r] 挂买单，股票[%s]/目标日期[%s]', date2str(today), code, date2str(trade_date))

        # 清仓
        if net_amount < lower:
            logger.debug('[%s] 北上资金流出净值[%.1f] < 布林下轨[%.1f]，全部清仓！', date2str(today), net_amount, lower)
            for code,position in self.broker.positions.items():
                logger.debug('[%s] 清仓[%s],股数[%.1f]', date2str(today), position.code, position.position)
                self.broker.sell_out(position.code, trade_date)

    def calculte_stock_rsrs(self, code):
        df = None
        # 缓存一下，否则，速度太慢了，计算一个需要3秒
        cache_zscore_csv = f"data/{code}_beta_zscore.csv"
        if os.path.exists(cache_zscore_csv):
            df = pd.read_csv(cache_zscore_csv,dtype={'code':str})
            df = set_date_index(df)
            logger.debug("加载调整zscore股票[%s]数据:%s", code, cache_zscore_csv)
        if df is None:  # 如果数据无缓存，就需要加载股票数据，并计算beta,r2,adjust_zscore
            print(code)
            df = data_loader.load_stock(code)
            df = self.calculate_rsrs(df)
            df.to_csv(cache_zscore_csv)
            logger.debug("保存[%s]调整zscore后的数据：%s", code, cache_zscore_csv)
        return df

    def calculate_rsrs(self, df):
        """
                loc = df.index.get_loc(today)
        df_recent = df.iloc[loc - self.params.N:loc]

        https://zhuanlan.zhihu.com/p/33501881
        https://www.joinquant.com/view/community/detail/b6c8d8ad459ac6188a77289916bc7407
        https://mp.weixin.qq.com/s/iX887oJw6gQ_mBRJaIyHQQ
        http://pg.jrj.com.cn/acc/Res/CN_RES/INVEST/2017/5/1/b4f37401-639d-493f-a810-38246b9c3c7d.pdf
        https://www.joinquant.com/algorithm/index/edit?algorithmId=230d7347cc4fc756a13f360f0529623c

        用最低价去拟合最高价，计算出beta来，用的是18天的数据

        第一种方法是直接将斜率作为指标值。当日RSRS斜率指标择时策略如下：
        1、取前N日最高价与最低价序列。（N = 18）
        2、将两个序列进行OLS线性回归。
        3、将拟合后的β值作为当日RSRS斜率指标值。
        4、当RSRS斜率大于S(buy)时，全仓买入，小于S(sell)时，卖出平仓。（S(buy)=1,S(sell)=0.8）

        high = alpha + beta * low + epsilon
        :param df:
        :param today:
        :return:
        """

        def clac_rsrs(close):
            """
            计算18天内的最高和最低价的beta值
            high = alpha + beta * low + epsilon
            """
            df_periods = df.loc[close.index]
            params, r2 = OLS(df_periods.high, df_periods.low)
            if len(params)<2:
                logger.warning("最高最低价拟合斜率不存在，无法计算RSRS斜率")
                df.loc[close.index, ['beta', 'r2']] = [np.nan, np.nan]
                return 1
            beta = params[1]
            # 参考这种方法，解决rolling.apply无法返回多个结果的问题
            # https://stackoverflow.com/questions/62716558/pandas-apply-on-rolling-with-multi-column-output
            df.loc[close.index, ['beta', 'r2']] = [beta, r2]
            return 1  # 返回1是瞎返回的，

        def clac_adjust_zscore(close):
            """
            按照研报中说的，用rsrs(beta)250日的均值 * r2值，作为调整后的zscore
            :param close:
            :return:
            """
            df1 = df.loc[close.index]
            mean = df1.beta.mean()
            std = df1.beta.std()
            beta = df1.iloc[-1].beta
            r2 = df1.iloc[-1].r2
            zscore = (beta - mean) / std
            adjust_zscore = zscore * r2
            df.loc[close.index, ['zscore', 'adjust_zscore']] = [zscore, adjust_zscore]
            return 1

        # 先计算18天窗口期内的beta和r2
        df.close.rolling(window=self.params.N).apply(clac_rsrs, raw=False)
        logger.debug("计算了[%s]的[%d]天的beta和r2值",df.iloc[0].code, self.params.N)

        # 再计算250天窗口期的移动平均值
        df.beta.rolling(window=self.params.M).apply(clac_adjust_zscore, raw=False)
        logger.debug("计算了[%s]的[%d]天beta值的移动平均值", df.iloc[0].code, self.params.M)

        return df
