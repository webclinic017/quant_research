import logging

import pandas as pd

from backtest.strategy import Strategy
from triples.my.prepare_data import calc_bolling, calculte_stock_rsrs
from utils.utils import date2str

logger = logging.getLogger(__name__)


class TripleStrategy(Strategy):

    def __init__(self, broker, params):
        super().__init__(broker, None)
        self.params = params
        self.df_position = pd.DataFrame()

    def set_data(self, df_dict: dict, df_baseline=None):
        super().set_data(df_baseline, df_dict)
        self.df_flow = calc_bolling(df_dict['moneyflow'], self.params)
        self.df_stock_pool = df_dict['stock_pool']

    def get_score_thresholds(self, params, df, date):
        """
        根据rsrs研报:
            贝塔值bata的范围是：均值0.9，用s2表示下界，用s1表示上界
            zscore和adjust_zscore：均值0，用-s表示下界，用s表示上界
        :param params:
        :param df:
        :param date:
        :return:
        """
        if params.rsrs_type == 'beta':
            score = self.get_value(df, date, 'beta')
            upper_threshold = params.S1  # 上阈值
            lower_threshold = params.S2  # 下阈值
        elif params.rsrs_type == 'zscore':
            score = self.get_value(df, date, 'zscore')
            upper_threshold = params.S  # 下阈值
            lower_threshold = - params.S  # 上阈值
        elif params.rsrs_type == 'adjust_zscore':
            score = self.get_value(df, date, 'adjust_zscore')
            upper_threshold = params.S
            lower_threshold = - params.S
        else:
            raise ValueError(params.rsrs_type)

        # print("=====>",score, upper_threshold, lower_threshold)
        return score, upper_threshold, lower_threshold

    def next(self, today, trade_date):
        super().next(today, trade_date)

        s_flow = self.get_value(self.df_flow, index_key=today)
        if s_flow is None: return False

        north_money = s_flow.north_money
        upper = s_flow.upper
        lower = s_flow.lower

        # logger.debug("指标：净值[%.1f],上轨[%.1f],下轨[%.1f]",north_money,upper,lower)

        b_trade = False
        # 根据北上资金的净流入的布林通道开仓
        if north_money > upper:
            logger.debug('[%s] 北上资金流入净值[%.1f] > 布林上轨[%.1f]，开仓：', date2str(today), north_money, upper)

            # 获得今日的10大净流入股票，因为有沪市top10+深市top10，所有有20只
            df_today_stocks = self.get_value(self.df_stock_pool, today)
            if df_today_stocks is None:
                logger.warning('今日[%s]没有流入股票', date2str(today))
                return False
            # 按照净值流入从大到小排列（原作者是按照买入股份数，我没这个数据，用净流入资金更实在）
            if self.params.stock_select == 'by_north_money':
                df_today_stocks = df_today_stocks.sort_values(by='north_money', ascending=False)
            else:
                df_today_stocks = df_today_stocks.sort_values(by='share_ratio', ascending=False)
            df_today_stocks = df_today_stocks.iloc[self.params.top10_scope[0]:self.params.top10_scope[1]]

            # https://tushare.pro/document/2?doc_id=48
            buy_list = []
            for _, s_stock in df_today_stocks.iterrows():
                code = s_stock.code
                # 计算这只股票的rsrs值（beta值或zscore等）
                df = calculte_stock_rsrs(code, self.params)
                # 需要动态把这只股票加入到broker中（这个是为了后续做交易统计用）
                self.broker.add_data(code, df)
                # 获得这只股票当日的zcore、上界、下界等数据
                score, upper_threshold, lower_threshold = self.get_score_thresholds(self.params, df, today)
                if score is None:
                    logger.warning("[%s]在[%s]日的score分值为空，忽略它", code, date2str(today))
                    continue

                # 如果这只股票已经在持仓中
                if code in self.broker.positions.keys():
                    logger.debug("[%s] 已经在持仓中，检查是否需要卖出", code)
                    # 如果这只股票的score分值低于下阈值，就需要把这只股票卖出
                    if score < lower_threshold:
                        logger.debug("[%s] 持仓中，%s[%.5f] < 下阈值[%.5f]，清仓！",
                                     code,
                                     self.params.rsrs_type,
                                     score,
                                     lower_threshold)
                        self.broker.sell_out(code, trade_date)
                        logger.debug('[%r] 挂买单，股票[%s]/目标日期[%s]', date2str(today), code, date2str(trade_date))
                    # 如果在仓位内，但是未低于下阈值，继续持有
                    else:
                        logger.debug("[%s] 持仓中，%s[%.5f] > 下阈值[%.5f]，继续持有",
                                     code,
                                     self.params.rsrs_type,
                                     score,
                                     lower_threshold)
                # 如果这只股票未在持仓中
                else:
                    # 如果这只股票的score分值高于上阈值，就需要买入这只股票
                    if score > upper_threshold:
                        logger.debug("[%s] 未持仓，%s[%.5f] > 阈值[%.5f]，买入！",
                                     code,
                                     self.params.rsrs_type,
                                     score,
                                     upper_threshold)
                        # 先计入买入列表，后续集中处理
                        buy_list.append(code)
                        b_trade = True

            if len(buy_list) > 0:
                # 把手头的现金平均分配，买入所有的待买股票
                per_amount = self.broker.total_cash / len(buy_list)
                for code in buy_list:
                    # 挂买单，目标日期是明天（明早开盘价买入）
                    self.broker.buy(code, trade_date, amount=per_amount)
                    logger.debug('[%r] 挂买单，股票[%s]/目标日期[%s]', date2str(today), code, date2str(trade_date))
                b_trade = True
            # 记录开仓
            self.df_position = self.df_position.append({
                'date': today,
                'position': 'open',  # 开仓
                'north_money': north_money}, ignore_index=True)

        # 如果当日北上资金低于布林通道下阈值，全部持仓清仓
        if north_money < lower:
            logger.debug('[%s] 北上资金流入净值[%.1f] < 布林下轨[%.1f]，全部清仓！', date2str(today), north_money, lower)
            for code, position in self.broker.positions.items():
                # 清仓这只股票
                self.broker.sell_out(position.code, trade_date)
                logger.debug('[%s] 清仓[%s],股数[%.1f]', date2str(today), position.code, position.position)
                b_trade = True
            # 记录清仓
            self.df_position = self.df_position.append({
                'date': today,
                'position': 'close',  # 开仓
                'north_money': north_money}, ignore_index=True)

        return b_trade