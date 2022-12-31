import argparse
import logging

import pandas as pd
from pandas import DataFrame
from tabulate import tabulate

from dingtou.backtest.banker import Banker
from dingtou.utils import utils
from dingtou.backtest.backtester import BackTester
from dingtou.backtest.broker import Broker
from dingtou.backtest.data_loader import load_index, load_funds
from dingtou.backtest.stat import calculate_metrics
from dingtou.utils.utils import str2date, date2str
from dingtou.pyramid_v2.plot import plot
from dingtou.pyramid_v2.position_calculator import PositionCalculator
from dingtou.pyramid_v2.pyramid_v2_strategy import PyramidV2Strategy

logger = logging.getLogger(__name__)

stat_file_name = "debug/stat.csv"

"""
再test_timing基础上做的改进
"""


def backtest(df_baseline: DataFrame, funds_data: dict, args):
    banker = Banker() if args.bank else None
    broker = Broker(args.amount, banker)
    broker.set_buy_commission_rate(0.0001)  # 参考华宝证券：ETF手续费万1，单笔最低0.2元
    broker.set_sell_commission_rate(0)
    backtester = BackTester(broker, args.start_date, args.end_date, buy_day='today')
    policy = PositionCalculator(args.grid_share)
    strategy = PyramidV2Strategy(broker,
                                 policy,
                                 args.grid_height,
                                 args.quantile_positive,
                                 args.quantile_negative,
                                 args.ma,
                                 args.end_date)
    backtester.set_strategy(strategy)

    # 单独调用一个set_data，是因为里面要做特殊处理
    backtester.set_data(df_baseline, funds_data)

    # 运行回测！！！
    backtester.run()

    logger.info("buy ok：%d", strategy.buy_ok)
    logger.info("buy fail：%d", strategy.buy_fail)
    logger.info("sell ok：%d", strategy.sell_ok)
    logger.info("sell fail：%d", strategy.sell_fail)

    return broker.df_total_market_value, broker, banker


def print_trade_details(start_date, end_date, amount, df_baseline, fund_dict, df_portfolio, broker, banker):
    df_stat = DataFrame()
    # 如果是多只基金一起投资，挨个统计他们各自的情况
    for code, df_fund in fund_dict.items():
        df_fund = df_fund[(df_fund.index > start_date) & (df_fund.index < end_date)]
        df_portfolio = df_portfolio[(df_portfolio.index > start_date) & (df_portfolio.index < end_date)]
        if len(broker.df_trade_history) == 0:
            logger.warning("基金[%s] 在%s~%s未发生任何一笔交易", code,date2str(start_date),date2str(end_date))
            continue
        if len(df_fund) == 0:
            logger.warning("基金[%s] 在%s~%s的数据为空", code,date2str(start_date),date2str(end_date))
            continue
        # 统计这只基金的收益情况
        stat = calculate_metrics(df_portfolio, df_baseline, df_fund, broker, amount, start_date, end_date)
        stat["借钱总额"] = banker.debt
        stat["借钱次数"] = banker.debt_num

        # 打印，暂时注释掉
        for k, v in stat.items():
            logger.info("{:>20s} : {}".format(k, v))
        logger.info("=" * 80)
        df_stat = df_stat.append(stat, ignore_index=True)

    if len(df_stat) == 0: return df_stat

    # 打印交易记录
    logger.info("交易记录：")
    print(tabulate(broker.df_trade_history, headers='keys', tablefmt='psql'))

    # 打印期末持仓情况
    logger.info("期末持仓：")
    df = DataFrame([p.to_dict() for code, p in broker.positions.items()])
    print(tabulate(df, headers='keys', tablefmt='psql'))

    # 把统计结果df_stat写入到csv文件
    logger.info("交易统计：")
    with pd.option_context('display.max_rows', 100, 'display.max_columns', 100):
        # df = df_stat[["基金代码","投资起始","投资结束","期初资金","期末现金","期末持仓","期末总值","组合收益率","组合年化","本金投入","本金投入","资金利用率","基准收益","基金收益","买次","卖次","持仓","成本","现价"]]
        # df = df_stat[["基金代码", "投资起始", "投资结束", "期初资金", "期末现金", "期末持仓", "期末总值", "组合收益",
        #               "组合年化", "资金利用率", "基准收益", "基金收益", "买次", "卖次"]]
        print(tabulate(df, headers='keys', tablefmt='psql'))
    df_stat.to_csv(stat_file_name)

    return df_stat


def main(args):
    df_baseline = load_index(index_code=args.baseline)

    # 加载基金数据，标准化列名，close是为了和标准的指数的close看齐
    fund_dict = load_funds(codes=args.code.split(","))

    df_portfolio, broker, banker = backtest(
        df_baseline,
        fund_dict,
        args)

    df_portfolio.sort_values('date')
    df_portfolio.set_index('date', inplace=True)

    # 统一过滤一下时间区间,
    start_date = str2date(args.start_date)
    end_date = str2date(args.end_date)

    df_baseline = df_baseline[(df_baseline.index > start_date) & (df_baseline.index < end_date)]
    df_portfolio = df_portfolio[(df_portfolio.index > start_date) & (df_portfolio.index < end_date)]

    # 打印交易统计和细节
    if banker:
        amount = banker.debt + args.amount
    else:
        amount = args.amount
    df_stat = print_trade_details(start_date,
                                  end_date,
                                  amount,
                                  df_baseline,
                                  fund_dict,
                                  df_portfolio,
                                  broker,
                                  banker)

    # 每只基金都给他单独画一个收益图
    plot(start_date, end_date, broker, df_baseline, df_portfolio, fund_dict, df_stat)

    return df_stat


"""
# 手工测试目前最优 ,512000,512560
python -m dingtou.pyramid_v2.pyramid_v2 \
-c 510310,510500,159915,588090 \
-s 20130101 \
-e 20230101 \
-b sh000001 \
-a 0 \
-m -480 \
-gs 1000 \
-gh 0.01 \
-qp 0.8 \
-qn 0.2 \
-bk
# -m 480， -gs 1000， -a 50万，这几个组合是比较最优的了


python -m dingtou.pyramid_v2.pyramid_v2 -c 510310,510500,159915,588090 -s 20130101 -e 20230101 -b sh000001 
["510050","510310","510500","512000","512560","512600"]
510050,510310,510500,512000,512560,512600

挑选选择：1、时间足够长；2、价格不是很贵（未拆分）：
- 华夏上证50ETF 510050  / 2014
- 沪深300ETF易方达 510310 / 2013
- 南方中证500ETF 510500 / 2013

- 券商ETF 512000
- 易方达中证军工ETF 512560 / 2017
- 嘉实中证主要消费ETF 512600  / 2014
"""
if __name__ == '__main__':
    utils.init_logger(file=True)

    # 获得参数
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--start_date', type=str, default="20150101", help="开始日期")
    parser.add_argument('-e', '--end_date', type=str, default="20221201", help="结束日期")
    parser.add_argument('-b', '--baseline', type=str, default=None, help="基准指数，这个策略里就是基金本身")
    parser.add_argument('-c', '--code', type=str, help="股票代码")
    parser.add_argument('-a', '--amount', type=int, default=200000, help="投资金额，默认50万")
    parser.add_argument('-bk', '--bank', action='store_true')
    parser.add_argument('-m', '--ma', type=int, default=-480, help=">0:间隔ma天的移动均线,<0:回看的最大最小值的均值")
    parser.add_argument('-gh', '--grid_height', type=float, default=0.02, help="格子的高度，百分比，默认1%")
    parser.add_argument('-gs', '--grid_share', type=int, default=100, help="每格子的基础份额")
    parser.add_argument('-qn', '--quantile_negative', type=float, default=0.3, help="均线下百分数区间")
    parser.add_argument('-qp', '--quantile_positive', type=float, default=0.3, help="均线上百分数区间")

    args = parser.parse_args()
    print(args)
    logger.info(args)
    main(args)
