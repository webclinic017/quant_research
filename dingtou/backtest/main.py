import argparse
import logging, os
import akshare as ak
import pandas as pd
from pandas import DataFrame

from backtest import utils
from backtest.backtester import BackTester
from backtest.broker import Broker
from backtest.cash_distribution import CashDistribute
from backtest.utils import date2str, str2date
from metrics import metrics as _metrics
import matplotlib.pyplot as plt

from backtest.strategy import  PeriodInvestStrategy

logger = logging.getLogger(__name__)




def backtest(df_baseline: DataFrame, funds_data: dict, start_date, end_date, amount, periods, sma_periods):
    broker = Broker(amount)
    backtester = BackTester(broker,start_date,end_date)
    backtester.set_strategy(PeriodInvestStrategy(broker, CashDistribute(amount, periods), sma_periods))
    # data，单独调用一个set_data，是因为要做特殊处理
    backtester.set_data(df_baseline, funds_data)

    # 运行回测！！！
    backtester.run()
    return broker.df_values,broker

def metrics(df_portfolio,df_baseline,df_fund,broker):
    # 得到组合的每日市值，并设置日期索引（为了后续的merge）

    # 和基准指数做一个合并，基准列只保留3列
    df_baseline = df_baseline.rename(columns={'close': 'index_close', 'pct_chg': 'pct_chg_baseline'})
    df_baseline['next_pct_chg_baseline'] = df_baseline.pct_chg_baseline.shift(-1)
    df_portfolio = df_portfolio.join(df_baseline[['index_close', 'pct_chg_baseline', 'next_pct_chg_baseline']])

    # 准备pct、next_pct_chg、和cumulative_xxxx
    df_portfolio['pct_chg'] = df_portfolio.total_value.pct_change()
    df_portfolio['next_pct_chg'] = df_portfolio.pct_chg.shift(-1)
    df_portfolio[['cumulative_pct_chg', 'cumulative_pct_chg_baseline']] = \
        df_portfolio[['next_pct_chg', 'next_pct_chg_baseline']].apply(lambda x: (x + 1).cumprod() - 1)

    df_portfolio = df_portfolio[~df_portfolio.cumulative_pct_chg.isna()]
    #
    # save_path = 'data/plot_{}_{}.jpg'.format(start_date, end_date)
    # plot_result(df_portfolio, save_path)

    # 计算各项指标
    logger.info("\t交易统计：")
    logger.info("\t\t定投起始：%r~%r",
                date2str(broker.trade_history[0].target_date),
                date2str(broker.trade_history[-1].target_date))
    logger.info("\t\t买入次数：%.0f", len(broker.trade_history))
    logger.info("\t\t佣金总额：%.2f", broker.total_commission)
    logger.info("\t\t持有现金：%.2f", broker.cash)
    logger.info("\t\t持仓价值：%.2f", broker.df_values.iloc[-1].total_value)
    logger.info("\t\t基准收益：%.1f%%",
                ((df_fund.iloc[-1].value - df_fund.iloc[0].value)/df_fund.iloc[0].value)*100)
    # print(df_baseline)
    # import pdb;pdb.set_trace()
    logger.info("\t\t大盘收益：%.1f%%",
                ((df_baseline.iloc[-1].index_close - df_baseline.iloc[0].index_close) / df_baseline.iloc[0].index_close) * 100)
    _metrics(df_portfolio)

    return df_portfolio



def load(name, func, **kwargs):
    print(f"加载{name}数据，函数:{func.__name__}，参数:{kwargs}")
    if not os.path.exists("data"): os.mkdir("data")
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
    df_fund = load(fund_code,ak.fund_open_fund_info_em,fund=fund_code, indicator="累计净值走势")
    df_fund['净值日期'] = pd.to_datetime(df_fund['净值日期'], format='%Y-%m-%d')
    return df_fund

def load_calendar(start_date, end_date):
    df = load("trade_date", ak.tool_trade_date_hist_sina)
#    df = df[(df.trade_date > start_date) & (df.trade_date < end_date)]
    print("加载交易日期：%r~%r" % (df.iloc[0], df.iloc[-1]))
    return df


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


def plot(df_baseline, df_fund, df_portfolio):

    plt.title("数据展示")
    fig = plt.figure(figsize=(50, 10), dpi=(200))
    plt.xticks(rotation=45)

    # 设置X轴
    ax_index = fig.add_subplot(111)
    ax_index.set_xlabel('日期')  # 设置x轴标题
    ax_index.set_ylabel('指数', color='r')  # 设置Y轴标题

    # 设置Y轴
    ax_fund = ax_index.twinx()
    ax_fund.set_ylabel('基金', color='b')  # 设置Y轴标题

    # 设置Y轴
    ax_portfolio = ax_index.twinx()
    ax_portfolio.set_ylabel('投资组合', color='c')  # 设置Y轴标题
    ax_portfolio.spines['right'].set_position(('outward', 60))  # right, left, top, bottom

    # 画指数和均线
    h_baseline_close, = ax_index.plot(df_baseline.index, df_baseline.close, 'r')
    h_baseline_sma, = ax_index.plot(df_baseline.index, df_baseline.sma, 'g')

    # 画涨跌
    ax_index.scatter(df_baseline.index, df_baseline.long, c='r', s=10)
    ax_index.scatter(df_baseline.index, df_baseline.short, c='g', s=10)
    ax_index.scatter(df_baseline.index, df_baseline.signal, marker='^', c='b', s=20)

    # 画基金
    h_fund, = ax_fund.plot(df_fund.index, df_fund.value, 'b')

    # 画组合收益
    h_portfolio, = ax_portfolio.plot(df_portfolio.index, df_portfolio.total_value, 'c')

    plt.legend(handles=[h_baseline_close,h_baseline_sma,h_fund,h_portfolio],
               labels=['指数', '指数均线', '基金', '投资组合'],
               loc='best')

    # 保存图片
    fig.savefig("debug/data.svg",  dpi=200, format='svg')


"""
指数代码：https://q.stock.sohu.com/cn/zs.shtml
sh000001: 上证指数
sh000300: 沪深300
sh000016：上证50
sh000905：中证500
sh000906：中证800
sh000852：中证1000

基金：
000960 招商医药
003095 中欧医疗
010437 嘉实竞争
005827 易方达蓝筹

python -m backtest.main -c 003095 -s 20150101 -e 20221201 -b sh000905
python -m backtest.main -c 003095 -s 20220101 -e 20221201 -b sh000905 && open debug/data.svg
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
    parser.add_argument('-p', '--periods', type=int, default=50, help="投资期数（周）")
    args = parser.parse_args()

    # 加载基准指数数据（周频）
    df_baseline = load_index(index_code=args.baseline)  # ,period='week')
    df_baseline['code'] = args.baseline  # 都追加一个code字段
    df_baseline = df_baseline.set_index('date')

    df_baseline = day2week(df_baseline)  # 由日频改为周频，必须是要日期为索引列，这个是day2week函数要求的

    # 加载基金数据
    df_fund = load_fund(fund_code=args.code)
    df_fund['code'] = args.code  # 都追加一个code字段
    df_fund.rename(columns={'净值日期': 'date', '累计净值': 'value'}, inplace=True)

    df_calendar = load_calendar(args.start_date, args.end_date)

    # 思来想去，还是分开了baseline和funds（支持多只）

    df_portfolio,broker = backtest(
        df_baseline,
        {args.code: df_fund},
        args.start_date,
        args.end_date,
        args.amount,
        args.periods,
        args.baseline_sma)
    df_portfolio.sort_values('trade_date')
    df_portfolio.set_index('trade_date', inplace=True)

    # 统一过滤一下时间区间
    start_date = str2date(args.start_date)
    end_date = str2date(args.end_date)
    df_baseline = df_baseline[(df_baseline.index > start_date) & (df_baseline.index < end_date)]
    df_fund = df_fund[(df_fund.index > start_date) & (df_fund.index < end_date)]
    df_portfolio = df_portfolio[(df_portfolio.index > start_date) & (df_portfolio.index < end_date)]


    metrics(df_portfolio,df_baseline,df_fund,broker)

    # 画图
    plot(df_baseline, df_fund, df_portfolio)
