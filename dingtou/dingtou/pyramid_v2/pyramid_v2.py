import argparse
import logging

import pandas as pd
from pandas import DataFrame

from dingtou.utils import utils
from dingtou.backtest.backtester import BackTester
from dingtou.backtest.broker import Broker
from dingtou.backtest.data_loader import load_fund, load_index, load_funds
from dingtou.backtest.stat import calculate_metrics
from dingtou.utils.utils import str2date
from dingtou.pyramid_v2.plot import plot
from dingtou.pyramid_v2.position_calculator import PositionCalculator
from dingtou.pyramid_v2.pyramid_v2_strategy import PyramidV2Strategy

logger = logging.getLogger(__name__)

"""
再test_timing基础上做的改进
"""


def backtest(df_baseline: DataFrame,
             funds_data: dict,
             start_date,
             end_date,
             amount,
             grid_height,
             grid_share,
             overlap_grid_num,
             ma_days):
    # 上来是0元
    broker = Broker(amount)
    broker.set_buy_commission_rate(0.0001)  # 参考华宝证券：ETF手续费万1，单笔最低0.2元
    broker.set_sell_commission_rate(0)
    backtester = BackTester(broker, start_date, end_date,buy_day='today')
    policy = PositionCalculator(overlap_grid_num,grid_share)
    strategy = PyramidV2Strategy(broker, policy, grid_height, overlap_grid_num,ma_days,end_date)
    backtester.set_strategy(strategy)
    # 单独调用一个set_data，是因为里面要做特殊处理
    backtester.set_data(df_baseline, funds_data)

    # 运行回测！！！
    backtester.run()

    logger.info("buy ok：%d",strategy.buy_ok)
    logger.info("buy fail：%d", strategy.buy_fail)
    logger.info("sell ok：%d", strategy.sell_ok)
    logger.info("sell fail：%d", strategy.sell_fail)

    return broker.df_total_market_value, broker


def main(args, stat_file_name="debug/stat.csv", plot_file_subfix='one'):
    # 加载基准指数数据（周频），如果没有设，就用基金自己；如果是sh开头，加载指数，否则，当做基金加载
    if args.baseline is None:
        df_baseline = load_fund(code=args.code)
    elif "sh" in args.baseline:
        df_baseline = load_index(index_code=args.baseline)
    else:
        df_baseline = load_fund(code=args.baseline)

    # 加载基金数据，标准化列名，close是为了和标准的指数的close看齐
    fund_dict = load_funds(codes=args.code.split(","))

    # 思来想去，还是分开了baseline和funds（支持多只）的数据

    df_portfolio, broker = backtest(
        df_baseline,
        fund_dict,
        args.start_date,
        args.end_date,
        args.amount,
        args.grid_height,
        args.grid_share,
        args.overlap,
        args.ma)
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
        stat = calculate_metrics(df_portfolio, df_baseline, df_fund, broker, args.amount,start_date,end_date)
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
python -m dingtou.pyramid_v2.pyramid_v2 \
-c 510500 \
-s 20190101 \
-e 20230101 \
-b sh000001 \
-a 200000 \
-m -720 \
-gs 100 \
-gh 0.01 \
-o 3

挑选选择：1、时间足够长；2、价格不是很贵（未拆分）：
- 华夏上证50ETF 510050  / 2014
- 沪深300ETF易方达 510310 / 2013
- 南方中证500ETF 510500 / 2013

- 券商ETF 512000
- 易方达中证军工ETF 512560 / 2017
- 嘉实中证主要消费ETF 512600  / 2014
"""
if __name__ == '__main__':
    utils.init_logger()

    # 获得参数
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--start_date', type=str, default="20150101", help="开始日期")
    parser.add_argument('-e', '--end_date', type=str, default="20221201", help="结束日期")
    parser.add_argument('-b', '--baseline', type=str, default=None, help="基准指数，这个策略里就是基金本身")
    parser.add_argument('-c', '--code', type=str, help="股票代码")
    parser.add_argument('-a', '--amount', type=int, default=500000, help="投资金额，默认50万")
    parser.add_argument('-m', '--ma', type=int, default=10, help=">0:间隔ma天的移动均线,<0:回看的最大最小值的均值")
    parser.add_argument('-gh', '--grid_height', type=float, default=0.01, help="格子的高度，百分比，默认1%")
    parser.add_argument('-gs', '--grid_share', type=int, default=100, help="每格子的基础份额")
    parser.add_argument('-o', '--overlap', type=int, default=3, help="对敲区间（格子数）")

    args = parser.parse_args()
    logger.info(args)
    main(args)
