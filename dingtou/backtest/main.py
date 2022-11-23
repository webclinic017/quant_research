import argparse
import logging, os
import akshare as ak
import pandas as pd
from backtest import utils
from backtest.backtester import BackTester
from backtest.broker import Broker
from backtest.cash_distribution import CashDistribute
from metrics import metrics
import matplotlib
import matplotlib.pyplot as plt
import talib
import numpy as np
from matplotlib.font_manager import FontProperties

from backtest.strategy import Strategy, PeriodInvestStrategy

logger = logging.getLogger(__name__)


def get_calendar(start_date, end_date):
    df = load("trade_date", ak.tool_trade_date_hist_sina)
    df = df[(df.trade_date > start_date) & (df.trade_date < end_date)]
    print("加载交易日期：%r~%r" % (df.iloc[0], df.iloc[-1]))
    return df


def backtest(data, start_date, end_date, amount, periods, sma_periods):
    broker = Broker(amount)
    backtester = BackTester(broker)
    backtester.set_strategy(PeriodInvestStrategy(broker,CashDistribute(amount, periods),sma_periods))
    backtester.set_data(data)
    backtester.run()

    # df_portfolio = broker.df_values
    # df_portfolio.sort_values('trade_date')
    #
    # # 只筛出来周频的市值来
    # df_portfolio = df_baseline.merge(df_portfolio, how='left', on='trade_date')
    #
    # # 拼接上指数
    # df_index = df_index[['trade_date', 'close']]
    # df_index = df_index.rename(columns={'close': 'index_close'})
    # df_portfolio = df_portfolio.merge(df_index, how='left', on='trade_date')
    #
    # # 准备pct、next_pct_chg、和cumulative_xxxx
    # df_portfolio = df_portfolio.sort_values('trade_date')
    # df_portfolio['pct_chg'] = df_portfolio.total_value.pct_change()
    # df_portfolio['next_pct_chg'] = df_portfolio.pct_chg.shift(-1)
    # df_portfolio[['cumulative_pct_chg', 'cumulative_pct_chg_baseline']] = \
    #     df_portfolio[['next_pct_chg', 'next_pct_chg_baseline']].apply(lambda x: (x + 1).cumprod() - 1)
    #
    # df_portfolio = df_portfolio[~df_portfolio.cumulative_pct_chg.isna()]
    #
    # save_path = 'data/plot_{}_{}_top{}.jpg'.format(start_date, end_date, top_n)
    # plot(df_portfolio, save_path)
    #
    # # 计算各项指标
    # logger.info("佣金总额：%.2f", broker.total_commission)
    # metrics(df_portfolio)


def load(name, func, **kwargs):
    print(f"加载{name}数据，函数:{func.__name__}，参数:{kwargs}")
    if not os.path.exists("../data"): os.mkdir("../data")
    file_name = f"data/{name}.csv"
    if not os.path.exists(file_name):
        df = func(**kwargs)
        print(f"调用了函数:{func.__name__}")
        df.to_csv(file_name)
    else:
        print(f"加载缓存文件:{file_name}")
        df = pd.read_csv(file_name)
    print(df)
    return df


def load_index(index_code):
    df_stock_index = load(index_code, ak.stock_zh_index_daily, symbol=index_code)
    df_stock_index['date'] = pd.to_datetime(df_stock_index['date'], format='%Y-%m-%d')
    return df_stock_index


def load_fund(fund_code):
    fund_file = f"{fund_code}.csv"
    if not os.path.exists(f"{fund_code}.csv"):
        df_fund = ak.fund_open_fund_info_em(fund=fund_code, indicator="累计净值走势")
        df_fund.to_csv(fund_file)
    else:
        df_fund = pd.read_csv(fund_file)

    df_fund['净值日期'] = pd.to_datetime(df_fund['净值日期'], format='%Y-%m-%d')
    return df_fund


def __calc_OHLC_in_group(df_in_group):
    """
    计算一个分组内的最大的、最小的、开盘、收盘 4个值
    """
    # 先复制最后一条（即周五或者月末日），为了得到所有的字段
    df_result = df_in_group.tail(1).copy()
    df_result['open'] = df_in_group.loc[df_in_group.index.min()]['open']
    df_result['close'] = df_in_group.loc[df_in_group.index.max()]['close']
    df_result['high'] = df_in_group['high'].max()
    df_result['low'] = df_in_group['low'].min()
    df_result['volume'] = df_in_group['volume'].sum()
    return df_result


def day2week(df):
    """
    返回，数据中，每周，最后一天的数据

    使用分组groupby返回的结果中多出一列，所以要用dropLevel 来drop掉
                                           code      open      high       low  ...   change   pct_chg      volume       amount
    datetime              datetime                                             ...
    2007-12-31/2008-01-06 2008-01-04  000636.SZ  201.0078  224.9373  201.0078  ...  -1.4360       NaN   352571.00   479689.500
    2008-01-07/2008-01-13 2008-01-11  000636.SZ  217.7585  223.1825  201.0078  ...  -6.5400 -0.027086   803621.33  1067058.340
    """
    # to_period是转成
    df_result = df.groupby(df.index.to_period('W')).apply(__calc_OHLC_in_group)
    if len(df_result.index.names) > 1:
        df_result = df_result.droplevel(level=0)  # 多出一列datetime，所以要drop掉
    df_result['pct_chg'] = df_result.close.pct_change()
    return df_result

def plot(df_baseline, df_fund):

    plt.title("数据展示")
    fig = plt.figure(figsize=(50, 10) ,dpi=(200))

    # 设置X轴
    ax_index = fig.add_subplot(111)
    ax_index.set_xlabel('日期')  # 设置x轴标题
    plt.xticks(rotation=45)

    # 设置Y轴
    ax_fund = ax_index.twinx()
    # ax_fit_k = ax_index.twinx()
    # ax_fit_k.spines['right'].set_position(('outward', 60))  # right, left, top, bottom

    # 画指数和均线
    ax_index.plot(df_baseline.index, df_baseline.close, 'r')
    ax_index.plot(df_baseline.index, df_baseline.sma, 'g')
    ax_index.set_ylabel('指数', color='r')  # 设置Y轴标题

    # 画涨跌
    ax_index.scatter(df_baseline.index, df_baseline.long, c='r',s=10)
    ax_index.scatter(df_baseline.index, df_baseline.short, c='g',s=10)
    ax_index.scatter(df_baseline.index, df_baseline.signal,marker='^',c='b',s=20)

    # 画基金
    ax_fund.plot(df_fund.index, df_fund.value, 'b')
    ax_fund.set_ylabel('基金', color='b')  # 设置Y轴标题


    # 保存图片
    fig.savefig("debug/data.svg", format='svg', dpi=200)

"""
指数代码：https://q.stock.sohu.com/cn/zs.shtml

sh000001: 上证指数
sh000300: 沪深300
sh000016：上证50
sh000905：中证500
sh000906：中证800
sh000852：中证1000

python -m backtest.main -c 000960 -s 20150101 -e 20220101 -b sh000905
"""
if __name__ == '__main__':
    utils.init_logger()

    # 获得参数
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--start_date', type=str, default="20150101", help="开始日期")
    parser.add_argument('-e', '--end_date', type=str, default="20221201", help="结束日期")
    parser.add_argument('-b', '--baseline', type=str, help="基准指数")
    parser.add_argument('-bma', '--baseline_sma', type=int, default=52, help="基准指数的移动均值周期数")
    parser.add_argument('-c', '--code', type=str, help="股票代码")
    parser.add_argument('-a', '--amount', type=int, default=500000, help="投资金额")
    parser.add_argument('-p', '--periods', type=int, default=52*5, help="投资期数（周）")
    args = parser.parse_args()

    # 加载基准指数数据（周频）
    df_baseline = load_index(index_code=args.baseline)  # ,period='week')
    df_baseline['code'] =args.baseline # 都追加一个code字段
    df_baseline = df_baseline.set_index('date')
    df_baseline = day2week(df_baseline)  # 由日频改为周频，必须是要日期为索引列，这个是day2week函数要求的

    # 加载基金数据
    df_fund = load_fund(fund_code=args.code)
    df_fund['code'] = args.code# 都追加一个code字段
    df_fund.rename(columns={'净值日期': 'date','累计净值': 'value'}, inplace=True)

    df_calendar = get_calendar(args.start_date, args.end_date)

    data = {'index': df_baseline, 'fund': df_fund}
    backtest(data, args.start_date,
             args.end_date, args.amount,
             args.periods, args.baseline_sma)

    print(df_baseline.columns)

    df_baseline = df_baseline[(df_baseline.index>args.start_date) & (df_baseline.index<args.end_date)]
    df_fund = df_fund[(df_fund.index > args.start_date) & (df_fund.index < args.end_date)]

    # 画图
    plot(df_baseline, df_fund)
