import logging
import os

import numpy as np
import pandas as pd

from utils import data_loader
from utils.data_loader import set_date_index
from utils.utils import OLS

logger = logging.getLogger(__name__)


def calculte_stock_rsrs(code, params):
    """
    计算股票对应的rsrs值，包括beta、zscore、adjust_zscore等，
    并缓存到data目录下，方便下次加速
    :param code: 股票代码
    :return: 返回加载后，并计算了rsrs值的dataframe
    """

    df = None
    # 缓存一下，否则，速度太慢了，计算一个需要3秒
    cache_zscore_csv = f"data/{code}_beta_zscore_N{params.N}_M{params.M}.csv"
    if os.path.exists(cache_zscore_csv):
        df = pd.read_csv(cache_zscore_csv, dtype={'code': str})
        df = set_date_index(df)
        # logger.debug("加载调整zscore股票[%s]数据:%s", code, cache_zscore_csv)
    if df is None:  # 如果数据无缓存，就需要加载股票数据，并计算beta,r2,adjust_zscore
        df = data_loader.load_stock(code)
        # 计算这一只股票每天的rsrs值
        df = calculate_rsrs(df, params)
        df.to_csv(cache_zscore_csv)
        logger.debug("保存[%s]调整zscore后的数据：%s", code, cache_zscore_csv)
    return df


def calculate_rsrs(df, params):
    """
            loc = df.index.get_loc(today)
    df_recent = df.iloc[loc - params.N:loc]

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

    def claculate_rsrs(close):
        """
        计算18天内的最高和最低价的beta值
        high = alpha + beta * low + epsilon
        """
        df_periods = df.loc[close.index]
        params, r2 = OLS(df_periods.low, df_periods.high)
        if len(params) < 2:
            # logger.warning("最高最低价拟合斜率不存在，无法计算RSRS斜率")
            df.loc[close.index, ['beta', 'r2']] = [np.nan, np.nan]
            return 1
        beta = params[1]
        # 参考这种方法，解决rolling.apply无法返回多个结果的问题
        # https://stackoverflow.com/questions/62716558/pandas-apply-on-rolling-with-multi-column-output
        df.loc[close.index, ['beta', 'r2']] = [beta, r2]
        return 1  # 返回1是瞎返回的，没用，更新其实发生在上一行

    def claculate_adjust_zscore(close, params):
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
    df.close.rolling(window=params.N).apply(claculate_rsrs, raw=False)
    logger.debug("计算了[%s]的[%d]天的beta和r2值", df.iloc[0].code, params.N)

    # 再计算600天窗口期的移动平均值
    df.beta.rolling(window=params.M).apply(claculate_adjust_zscore, raw=False)
    logger.debug("计算了[%s]的[%d]天beta值的移动平均值", df.iloc[0].code, params.M)

    return df


def calc_bolling(df_flow, params):
    """
    1. 计算布林通道。

    https://tushare.pro/document/2?doc_id=47
    north_money	float	北向资金（百万元）
    south_money	float	南向资金（百万元）
       trade_date  ggt_ss  ggt_sz      hgt      sgt  north_money  south_money
    0    20180808  -476.0  -188.0   962.68   799.94      1762.62       -664.0
    1    20180807  -261.0   177.0  2140.85  1079.82      3220.67        -84.0

    中轨线 = 90日的移动平均线（SMA)
    上轨线 = 90日的SMA +（90日的标准差 x 2）
    下轨线 = 90日的SMA -（90日的标准差 x 2）
    """

    # 不能用talib，因为中间有一些na，会导致它全都变成na了，用dataframe.rolling替代
    df_flow['_mid'] = df_flow.north_money.rolling(window=params.bolling_period, min_periods=1).mean()
    df_flow['_std'] = df_flow.north_money.rolling(window=params.bolling_period, min_periods=1).std()
    df_flow['upper'] = df_flow._mid + params.bolling_std * df_flow._std
    df_flow['lower'] = df_flow._mid - params.bolling_std * df_flow._std

    return df_flow
