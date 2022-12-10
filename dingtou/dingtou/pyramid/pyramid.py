import argparse
import logging

import matplotlib.pyplot as plt
import pandas as pd
from pandas import DataFrame

from dingtou.backtest import utils
from dingtou.backtest.backtester import BackTester
from dingtou.backtest.broker import Broker
from dingtou.backtest.data_loader import load_fund, load_index, load_funds, load_stocks
from dingtou.backtest.stat import calculate_metrics
from dingtou.backtest.utils import str2date
from dingtou.pyramid.grid_calculator import calculate_grid_values_by_statistics
from dingtou.pyramid.pyramid_policy import PyramidPolicy
from dingtou.pyramid.pyramid_strategy import PyramidStrategy

logger = logging.getLogger(__name__)

"""
再test_timing基础上做的改进
"""


def backtest(df_baseline: DataFrame,
             funds_data: dict,
             up_grid_height_dict: dict,
             down_grid_height_dict: dict,
             grid_share_dict: dict,
             start_date,
             end_date,
             amount):
    # 上来是0元
    broker = Broker(amount)
    broker.set_buy_commission_rate(0.0001)  # 参考华宝证券：ETF手续费万1，单笔最低0.2元
    broker.set_sell_commission_rate(0)
    backtester = BackTester(broker, start_date, end_date)
    policy = PyramidPolicy(grid_share_dict)
    strategy = PyramidStrategy(broker, policy, up_grid_height_dict,down_grid_height_dict)
    backtester.set_strategy(strategy)
    # 单独调用一个set_data，是因为里面要做特殊处理
    backtester.set_data(df_baseline, funds_data)

    # 运行回测！！！
    backtester.run()
    return broker.df_total_market_value, broker


def plot(df_baseline, df_fund, df_portfolio, df_buy_trades, df_sell_trades, plot_file_subfix):
    plt.clf()
    code = df_fund.iloc[0].code
    fig = plt.figure(figsize=(50, 10), dpi=(200))

    # 设置基准X轴
    ax_baseline = fig.add_subplot(111)
    ax_baseline.grid()
    ax_baseline.set_title(f"{code}投资报告")
    ax_baseline.set_xlabel('日期')  # 设置x轴标题

    # 画基准
    # h_baseline_close, = ax_baseline.plot(df_baseline.index, df_baseline.close, 'r')

    # --------------------------------------------------------

    # 设置单位净值Y轴
    ax_fund = ax_baseline.twinx()  # 返回共享x轴的第3个轴
    # ax_fund.set_ylabel('单位净值', color='b')  # 设置Y轴标题
    # 画单位净值日线
    # h_fund, = ax_fund.plot(df_fund.index, df_fund.close, 'b', linewidth=2)

    # --------------------------------------------------------

    # 画累计净值基金日线
    ax_fund_accumulate = ax_baseline.twinx()  # 返回共享x轴的第3个轴
    ax_fund_accumulate.set_ylabel('累计净值', color='g')  # 设置Y轴标题
    ax_fund_accumulate.spines['right'].set_position(('outward', 60))  # right, left, top, bottom
    h_fund_accumulate, = ax_fund_accumulate.plot(df_fund.index, df_fund.close, 'b', linewidth=2)
    # 画累计净值基金均线
    h_fund_sma, = ax_fund_accumulate.plot(df_fund.index, df_fund.ma, color='g', linestyle='--', linewidth=1)
    # 画买卖信号
    ax_fund_accumulate.scatter(df_buy_trades.actual_date, df_buy_trades.price, marker='^', c='r', s=40)
    # 不一定有卖
    if len(df_sell_trades) > 0:
        ax_fund_accumulate.scatter(df_sell_trades.actual_date, df_sell_trades.price, marker='v', c='g', s=40)
    # 画成我持仓成本线
    h_cost, = ax_fund_accumulate.plot(df_portfolio.index, df_portfolio.cost, 'm', linestyle='--', linewidth=0.5)

    # --------------------------------------------------------

    # 设置组合的Y轴
    ax_portfolio = ax_baseline.twinx()  # 返回共享x轴的第二个轴
    ax_portfolio.spines['right'].set_position(('outward', 120))  # right, left, top, bottom
    ax_portfolio.set_ylabel('投资组合', color='c')  # 设置Y轴标题

    # 画组合收益
    h_portfolio, = ax_portfolio.plot(df_portfolio.index, df_portfolio.total_value, 'c')

    plt.legend(handles=[h_portfolio, h_cost, h_fund_accumulate, h_fund_sma],
               labels=['投资组合', '成本线', '累计净值', '累计净值均线'],
               loc='best')

    # 保存图片
    fig.savefig(f"debug/{code}_report_{plot_file_subfix}.svg", dpi=200, format='svg')


def main(args, stat_file_name="debug/stat.csv", plot_file_subfix='one'):
    # 加载基准指数数据（周频），如果没有设，就用基金自己；如果是sh开头，加载指数，否则，当做基金加载
    if args.baseline is None:
        df_baseline = load_fund(code=args.code)
    elif "sh" in args.baseline:
        df_baseline = load_index(index_code=args.baseline)
    else:
        df_baseline = load_fund(code=args.baseline)

    # 加载基金数据，标准化列名，close是为了和标准的指数的close看齐

    if args.type == 'fund':
        fund_dict = load_funds(codes=args.code.split(","), ma_days=args.ma)
    else:
        fund_dict = load_stocks(codes=args.code.split(","), ma_days=args.ma)

    up_grid_height_dict, down_grid_height_dict, grid_share_dict = \
        calculate_grid_values_by_statistics(fund_dict, args.grid_amount, args.grid_num)

    # 思来想去，还是分开了baseline和funds（支持多只）的数据

    df_portfolio, broker = backtest(
        df_baseline,
        fund_dict,
        up_grid_height_dict,
        down_grid_height_dict,
        grid_share_dict,
        args.start_date,
        args.end_date,
        args.amount)
    df_portfolio.sort_values('date')
    df_portfolio.set_index('date', inplace=True)

    # 统一过滤一下时间区间,
    # 回测之后再过滤，会担心把start_date之前的也回测了，
    # 为何开始用全部数据，是因为要算移动平均，需要之前的历史数据
    # 而最后要显示和统计的时候，就需要只保留你关心的期间了
    start_date = str2date(args.start_date)
    end_date = str2date(args.end_date)
    df_baseline = df_baseline[(df_baseline.index > start_date) & (df_baseline.index < end_date)]

    df_stat = DataFrame()
    for code, df_fund in fund_dict.items():
        df_fund = df_fund[(df_fund.index > start_date) & (df_fund.index < end_date)]
        df_portfolio = df_portfolio[(df_portfolio.index > start_date) & (df_portfolio.index < end_date)]

        if broker.positions.get(df_fund.iloc[0].code, None) is None:
            logger.warning("基金[%s]未发生任何一笔交易", df_fund.iloc[0].code)
        stat = calculate_metrics(df_portfolio, df_baseline, df_fund, broker, args)
        df_stat = df_stat.append(stat, ignore_index=True)
        df_buy_trades = broker.df_trade_history[
            (broker.df_trade_history.code == code) & (broker.df_trade_history.action == 'buy')]
        df_sell_trades = broker.df_trade_history[
            (broker.df_trade_history.code == code) & (broker.df_trade_history.action == 'sell')]

        plot(df_baseline, df_fund, df_portfolio, df_buy_trades, df_sell_trades, plot_file_subfix)

    with pd.option_context('display.max_rows', 100, 'display.max_columns', 100):
        from tabulate import tabulate
        # df = df_stat[["基金代码","投资起始","投资结束","期初资金","期末现金","期末持仓","期末总值","组合收益率","组合年化","本金投入","本金投入","资金利用率","基准收益","基金收益","买次","卖次","持仓","成本","现价"]]
        df = df_stat[["基金代码", "投资起始", "投资结束", "期初资金", "期末现金", "期末持仓", "期末总值", "组合收益率",
                      "组合年化", "资金利用率", "基准收益", "基金收益", "买次", "卖次"]]
        print(tabulate(df, headers='keys', tablefmt='psql'))
    df_stat.to_csv(stat_file_name)
    return df_stat


"""
指数代码：https://q.stock.sohu.com/cn/zs.shtml
sh000001: 上证指数
sh000300: 沪深300
sh000016：上证50
sh000905：中证500
sh000906：中证800
sh000852：中证1000




python -m dingtou.pyramid.pyramid \ 
-c 512600 \
-s 20180101 \
-e 20210101 \
-b sh000001 \
-a 200000 \
-ga 2000

python -m dingtou.pyramid.pyramid \
-c 510310,510560,512000,512010,512040,512070,512330,512480,512560,512600 \
-s 20180101 \ 
-e 20210101 \
-b sh000001 \
-a 200000 


python -m dingtou.pyramid.pyramid \ 
-c 002583 \
-t stock \
-s 20180101 \
-e 20210101 \
-b sh000001 \
-a 200000 \
-ga 2000

"""
if __name__ == '__main__':
    utils.init_logger()

    # 获得参数
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--start_date', type=str, default="20150101", help="开始日期")
    parser.add_argument('-e', '--end_date', type=str, default="20221201", help="结束日期")
    parser.add_argument('-b', '--baseline', type=str, default=None, help="基准指数，这个策略里就是基金本身")
    parser.add_argument('-m', '--ma', type=int, default=240, help="基金的移动均值")
    parser.add_argument('-c', '--code', type=str, help="股票代码")
    parser.add_argument('-a', '--amount', type=int, default=500000, help="投资金额，默认50万")
    parser.add_argument('-t', '--type', type=str, default='fund', help="fund|stock")
    parser.add_argument('-ga', '--grid_amount', type=int, default=1000, help="每网格买入份数，默认1万")
    parser.add_argument('-gn', '--grid_num', type=int, default=10, help="格子的数量")
    args = parser.parse_args()
    logger.info(args)
    main(args)
