from datetime import datetime
import logging
import numpy as np
from dateutil.relativedelta import relativedelta
from empyrical import max_drawdown
import math
from research.utils import date2str
from empyrical import sortino_ratio as _sortino_ratio
from empyrical import calmar_ratio as _calmar_ratio

logger = logging.getLogger(__name__)

RISK_FREE_ANNUALLY_RETRUN = 0.03  # 在我国无风险收益率一般取值十年期国债收益，我查了一下有波动，取个大致的均值3%


def total_profit(df, key='close'):
    return (df.iloc[-1][key] - df.iloc[0][key]) / df.iloc[0][key]


def scope(start_date,end_date):
    years = relativedelta(dt1=end_date, dt2=start_date).years
    months = relativedelta(dt1=end_date, dt2=start_date).months % 12
    return f"{date2str(start_date)}~{date2str(end_date)}: {years}年{months}月"



def annually_profit(df, key='close'):
    """
    年化收益率：https://www.pynote.net/archives/1667
    计算公式是这样来的：初始市值A，期末市值B，N年，X为年化收益率，那么A*(1+X)^N=B，简单数学公式变形后，就是上面的计算方法。
    """
    # 累计收益
    earn = df.iloc[-1][key] / df.iloc[0][key]
    start_date = df.index.min()
    end_date = df.index.max()
    years = relativedelta(dt1=end_date, dt2=start_date).years
    months = relativedelta(dt1=end_date, dt2=start_date).months % 12
    years = years + months / 12
    return earn ** (1 / years) - 1



def volatility(df):
    """波动率"""
    return df['next_pct_chg'].std()


def sharp_ratio(series_pct_change, period='day'):
    """
    夏普比率 = 收益均值-无风险收益率 / 收益方差
    无风险收益率,在我国无风险收益率一般取值十年期国债收益
    https://rich01.com/what-sharpe-ratio/
        夏普率= [(每日報酬率平均值- 無風險利率) / (每日報酬的標準差)]x (252平方根)
        一個好的策略，取任何一段時間的夏普率，數值不應該有巨大的落差
         (la.mean()- 0.0285/252)/la.std()*np.sqrt(252)
    """
    if period == 'day':
        return (series_pct_change.mean() - RISK_FREE_ANNUALLY_RETRUN / 252) / series_pct_change.std() * math.sqrt(252)

    raise ValueError(f"未实现的周期{period}")


def sortino_ratio(series_pct_change):
    # https://blog.csdn.net/The_Time_Runner/article/details/99569365
    return _sortino_ratio(series_pct_change)


def calmar_ratio(series_pct_change):
    # https://blog.csdn.net/The_Time_Runner/article/details/99569365
    return _calmar_ratio(series_pct_change)


def max_drawback(series_pct_change):
    """
    from empyrical import max_drawdown， 输入是return，而不是close，注意
    最大回撤，https://www.yht7.com/news/30845
    """
    return max_drawdown(series_pct_change)


def annually_active_return(df):
    """年化主动收益率"""
    cumulative_active_return = df['cumulative_active_pct_chg'].iloc[-1] + 1
    total_weeks = len(df)
    return np.power(cumulative_active_return, 50 / total_weeks) - 1


def active_return_max_drawback(df):
    """年化主动收最大回撤"""
    pass


def annually_track_error(df):
    """年化跟踪误差"""


def information_ratio(df):
    """
    信息比率IR
    IR= IC的多周期均值/IC的标准方差，代表因子获取稳定Alpha的能力。当IR大于0.5时因子稳定获取超额收益能力较强。
    - https://www.zhihu.com/question/342944058
    - https://zhuanlan.zhihu.com/p/351462926
    讲人话：
    就是主动收益的均值/主动收益的方差
    """
    return df.active_pct_chg.mean() / df.active_pct_chg.std()


def win_rate(df):
    """胜率"""
    return (df['active_pct_chg'] > 0).sum() / len(df)
