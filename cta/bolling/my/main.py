import argparse
import logging

from pandas import DataFrame
from tabulate import tabulate

from backtest.backtester import BackTester
from backtest.broker import Broker
from backtest.stat import calculate_metrics
from bolling.my.bolling_strategy import BollingStrategy
from bolling.my.data import Data
from bolling.my.plot import plot
from utils import utils
from utils.utils import str2date, date2str

logger = logging.getLogger(__name__)

"""
再test_timing基础上做的改进
"""


def backtest(df_baseline: DataFrame, df_dict, params):
    # banker = Banker()
    banker = None
    broker = Broker(params.amount, banker)
    broker.set_buy_commission_rate(0.0002)
    broker.set_sell_commission_rate(0)
    backtester = BackTester(broker, params.start_date, params.end_date, buy_day='tomorrow')
    strategy = BollingStrategy(broker, params)
    backtester.set_strategy(strategy)

    # 单独调用一个set_data，是因为里面要做特殊处理
    # 这里的数据是全量数据（不是start_date~end_date的数据，原因是增大数据才能得到更客观的百分位数）
    backtester.set_data(df_dict, df_baseline)

    # 运行回测！！！
    backtester.run()

    return broker.df_total_market_value, broker, banker


def print_trade_details(start_date, end_date, amount, df_baseline, df_dict, df_portfolio, broker, banker):
    df_stat = DataFrame()
    # 如果是多只基金一起投资，挨个统计他们各自的情况
    for code, df_data in df_dict.items():
        if code in ['moneyflow','stock_pool','baseline']: continue

        df_data = df_data[(df_data.index > start_date) & (df_data.index < end_date)]
        df_portfolio = df_portfolio[(df_portfolio.index > start_date) & (df_portfolio.index < end_date)]
        if len(broker.df_trade_history) == 0:
            logger.warning("基金[%s] 在%s~%s未发生任何一笔交易", code, date2str(start_date), date2str(end_date))
            continue
        if len(df_data) == 0:
            logger.warning("基金[%s] 在%s~%s的数据为空", code, date2str(start_date), date2str(end_date))
            continue
        # 统计这只基金的收益情况
        stat = calculate_metrics(df_portfolio, df_baseline, df_data, broker, amount, start_date, end_date)
        stat["借钱总额"] = banker.debt if banker else 'N/A'
        stat["借钱次数"] = banker.debt_num if banker else 'N/A'

        if stat['买次']>0:
            # 打印，暂时注释掉
            for k, v in stat.items():
                logger.info("{:>20s} : {}".format(k, v))
            logger.info("=" * 80)
            df_stat = df_stat.append(stat, ignore_index=True)

    if len(df_stat) == 0: return df_stat

    codes = "_".join([k for k, v in df_dict.items()])[:100]
    stat_file_name = f"debug/stat_{date2str(start_date)}_{date2str(end_date)}_{codes}.csv"
    trade_file_name = f"debug/trade_{date2str(start_date)}_{date2str(end_date)}_{codes}.csv"

    # 打印交易记录
    logger.info("交易记录：")
    print(tabulate(broker.df_trade_history, headers='keys', tablefmt='psql'))
    broker.df_trade_history.to_csv(trade_file_name)

    # 打印期末持仓情况
    logger.info("期末持仓：")
    df = DataFrame([p.to_dict() for code, p in broker.positions.items()])
    print(tabulate(df, headers='keys', tablefmt='psql'))

    # 把统计结果df_stat写入到csv文件
    # logger.info("交易统计：")
    # with pd.option_context('display.max_rows', 100, 'display.max_columns', 100):
    #     # df = df_stat[["基金代码","投资起始","投资结束","期初资金","期末现金","期末持仓","期末总值","组合收益率","组合年化","本金投入","本金投入","资金利用率","基准收益","基金收益","买次","卖次","持仓","成本","现价"]]
    #     # df = df_stat[["基金代码", "投资起始", "投资结束", "期初资金", "期末现金", "期末持仓", "期末总值", "组合收益",
    #     #               "组合年化", "资金利用率", "基准收益", "基金收益", "买次", "卖次"]]
    #     print(tabulate(df, headers='keys', tablefmt='psql'))
    df_stat.to_csv(stat_file_name)

    return df_stat


def main(params):
    df_baseline, df_dict = Data().prepare(params)

    df_portfolio, broker, banker = backtest(df_baseline, df_dict, params)

    df_portfolio.sort_values('date')
    df_portfolio.set_index('date', inplace=True)

    # 统一过滤一下时间区间,
    start_date = str2date(params.start_date)
    end_date = str2date(params.end_date)

    df_baseline = df_baseline[(df_baseline.index > start_date) & (df_baseline.index < end_date)]
    df_portfolio = df_portfolio[(df_portfolio.index > start_date) & (df_portfolio.index < end_date)]

    # 打印交易统计和细节
    if banker:
        amount = banker.debt
    else:
        amount = params.amount
    df_stat = print_trade_details(start_date,
                                  end_date,
                                  amount,
                                  df_baseline,
                                  df_dict,
                                  df_portfolio,
                                  broker,
                                  banker)

    for code,df in df_dict.items():
        df_dict[code]= df[(df.index > start_date) & (df.index < end_date)]

    # 每只基金都给他单独画一个收益图
    plot(start_date, end_date, broker, df_baseline, df_portfolio, df_dict, df_stat)

    return df_stat


"""
python -m bolling.my.main
"""
if __name__ == '__main__':
    utils.init_logger(file=True)

    # 获得参数
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--conf', type=str, default="bolling/params.yml", help="参数文件路径")
    __params = parser.parse_args()
    params = utils.load_params(__params.conf)
    logger.info(params)
    main(params)
