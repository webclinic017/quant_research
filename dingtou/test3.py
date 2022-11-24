import argparse
import logging, os
import akshare as ak
import pandas as pd
from pandas import DataFrame

from backtest import utils
from backtest.backtester import BackTester
from backtest.broker import Broker
from backtest.cash_distribution import AverageCashDistribute
from backtest.utils import date2str, str2date, day2week
from period_strategy import PeriodStrategy
from backtest import metrics
import matplotlib.pyplot as plt

logger = logging.getLogger(__name__)


def backtest(df_baseline: DataFrame, funds_data: dict, start_date, end_date, amount, periods, sma_periods):
    broker = Broker(amount)
    backtester = BackTester(broker, start_date, end_date)
    backtester.set_strategy(PeriodStrategy(broker, AverageCashDistribute(amount, periods), sma_periods))
    # 单独调用一个set_data，是因为里面要做特殊处理
    backtester.set_data(df_baseline, funds_data)

    # 运行回测！！！
    backtester.run()
    return broker.df_values, broker


def calculate_metrics(df_portfolio, df_baseline, df_fund, broker):
    # 计算各项指标
    logger.info("\t交易统计：")
    logger.info("\t\t基金代码：%s", df_fund.iloc[0].code)
    logger.info("\t\t基准指数：%s", df_baseline.iloc[0].code)
    logger.info("\t\t投资起始：%r", metrics.scope(df_portfolio))
    logger.info("\t\t定投起始：%r~%r", date2str(broker.trade_history[0].target_date),
                date2str(broker.trade_history[-1].target_date))
    logger.info("\t\t组合收益：%.1f%% \t<---", metrics.total_profit(df_portfolio, key='total_value') * 100)
    logger.info("\t\t组合年化：%.1f%% \t\t<---", metrics.annually_profit(df_portfolio, key='total_value') * 100)
    logger.info("\t\t基准收益：%.1f%%", metrics.total_profit(df_baseline) * 100)
    logger.info("\t\t基金收益：%.1f%%", metrics.total_profit(df_fund) * 100)
    logger.info("\t\t买入次数：%.0f", len(broker.trade_history))
    logger.info("\t\t佣金总额：%.2f", broker.total_commission)
    logger.info("\t\t期末现金：%.2f", broker.cash)
    logger.info("\t\t期末持仓：%.2f", broker.df_values.iloc[-1].total_position_value)
    logger.info("\t\t期末总值：%.2f", broker.df_values.iloc[-1].total_value)

    return df_portfolio


def load(name, func, **kwargs):
    logger.info(f"加载{name}数据，函数:{func.__name__}，参数:{kwargs}")
    if not os.path.exists("data"): os.mkdir("data")
    file_name = f"data/{name}.csv"
    if not os.path.exists(file_name):
        df = func(**kwargs)
        logger.debug(f"调用了函数:{func.__name__}")
        df.to_csv(file_name)
    else:
        logger.debug(f"加载缓存文件:{file_name}")
        df = pd.read_csv(file_name)
    return df


def load_index(index_code):
    df_stock_index = load(index_code, ak.stock_zh_index_daily, symbol=index_code)
    df_stock_index['date'] = pd.to_datetime(df_stock_index['date'], format='%Y-%m-%d')
    df_stock_index['code'] = index_code  # 都追加一个code字段
    df_stock_index = df_stock_index.set_index('date')

    return df_stock_index


def load_fund(fund_code):
    df_fund = load(fund_code, ak.fund_open_fund_info_em, fund=fund_code, indicator="累计净值走势")
    df_fund['净值日期'] = pd.to_datetime(df_fund['净值日期'], format='%Y-%m-%d')
    df_fund['code'] = fund_code  # 都追加一个code字段
    df_fund.rename(columns={'净值日期': 'date', '累计净值': 'close'}, inplace=True)
    df_fund = df_fund.set_index('date')

    return df_fund


def load_calendar(start_date, end_date):
    df = load("trade_date", ak.tool_trade_date_hist_sina)
    #    df = df[(df.trade_date > start_date) & (df.trade_date < end_date)]
    print("加载交易日期：%r~%r" % (df.iloc[0], df.iloc[-1]))
    return df


def plot(df_baseline, df_fund, df_portfolio):
    code = df_fund.iloc[0].code

    plt.title(f"{code}投资报告")
    fig = plt.figure(figsize=(50, 10), dpi=(200))
    plt.xticks(rotation=45)

    # 设置X轴
    ax_baseline = fig.add_subplot(111)
    ax_baseline.set_xlabel('日期')  # 设置x轴标题
    ax_baseline.set_ylabel('指数', color='r')  # 设置Y轴标题

    # 设置Y轴
    ax_fund = ax_baseline
    ax_fund.set_ylabel('基金', color='b')  # 设置Y轴标题

    # 设置Y轴
    ax_portfolio = ax_baseline.twinx()
    ax_portfolio.set_ylabel('投资组合', color='c')  # 设置Y轴标题
    ax_portfolio.spines['right'].set_position(('outward', 60))  # right, left, top, bottom

    # 画指数和均线
    # h_baseline_close, = ax_baseline.plot(df_baseline.index, df_baseline.close, 'r')
    h_baseline_sma, = ax_baseline.plot(df_baseline.index, df_baseline.sma, color='g', linestyle='--',linewidth=0.5)

    # 画涨跌
    # ax_baseline.scatter(df_baseline.index, df_baseline.long, c='r', s=10)
    # ax_baseline.scatter(df_baseline.index, df_baseline.short, c='g', s=10)
    ax_baseline.scatter(df_baseline.index, df_baseline.signal, marker='^', c='r', s=20)
    ax_baseline.set_yticks([])

    # 画基金
    h_fund, = ax_fund.plot(df_fund.index, df_fund.close, 'b')

    # 画组合收益
    h_portfolio, = ax_portfolio.plot(df_portfolio.index, df_portfolio.total_value, 'c')

    plt.legend(handles=[h_baseline_sma, h_fund, h_portfolio],
               labels=['指数均线', '基金', '投资组合'],
               loc='best')

    # 保存图片
    fig.savefig(f"debug/{code}_report.svg", dpi=200, format='svg')


def main(code):
    # 加载基准指数数据（周频）
    if "sh" in args.baseline:
        df_baseline = load_index(index_code=args.baseline)
    else:
        df_baseline = load_fund(fund_code=args.baseline)

    df_baseline = day2week(df_baseline)  # 由日频改为周频，必须是要日期为索引列，这个是day2week函数要求的

    # 加载基金数据，标准化列名，close是为了和标准的指数的close看齐
    df_fund = load_fund(fund_code=code)

    # 思来想去，还是分开了baseline和funds（支持多只）的数据

    df_portfolio, broker = backtest(
        df_baseline,
        {code: df_fund},
        args.start_date,
        args.end_date,
        args.amount,
        args.periods,
        args.baseline_sma)
    df_portfolio.sort_values('trade_date')
    df_portfolio.set_index('trade_date', inplace=True)

    # 统一过滤一下时间区间,
    # 回测之后再过滤，会担心把start_date之前的也回测了，
    # 不用担心，
    start_date = str2date(args.start_date)
    end_date = str2date(args.end_date)
    df_baseline = df_baseline[(df_baseline.index > start_date) & (df_baseline.index < end_date)]
    df_fund = df_fund[(df_fund.index > start_date) & (df_fund.index < end_date)]
    df_portfolio = df_portfolio[(df_portfolio.index > start_date) & (df_portfolio.index < end_date)]

    calculate_metrics(df_portfolio, df_baseline, df_fund, broker)

    # 画图
    plot(df_baseline, df_fund, df_portfolio)


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
--------------
晨星筛选：
    https://www.morningstar.cn/quickrank/default.aspx
    (医药、消费、科技、灵活配置、中盘成长、中小盘积极；3、5年3星+；开放）
    100亿以内，夏普1+，
540008	汇丰晋信低碳先锋股票A
002910	易方达供给改革灵活配置混合
001606	农银汇理工业4.0灵活配置混合
000729	建信中小盘先锋股票A
090018	大成新锐产业混合
001643	汇丰晋信智造先锋股票A
001644	汇丰晋信智造先锋股票C
001822	华商智能生活灵活配置混合A
003567	华夏行业景气混合
000689	前海开源新经济灵活配置混合A

python -m test3 -c 003095 -s 20180101 -e 20221101 -b 003095 -p 150

测试3：
    这个基金不做择时了，就是定投
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
    parser.add_argument('-p', '--periods', type=int, default=52*3, help="投资期数（周）")
    args = parser.parse_args()

    if "," in args.code:
        for code in args.code:
            main(code)
    else:
        main(args.code)
