import argparse
import logging

import talib
from dateutil.relativedelta import relativedelta
from pandas import DataFrame
import pandas as pd
from dingtou.backtest import utils
from dingtou.backtest.backtester import BackTester
from dingtou.backtest.broker import Broker
from dingtou.backtest.data_loader import load_fund, load_index, load_funds
from dingtou.backtest.utils import date2str, str2date
from dingtou.backtest import metrics
import matplotlib.pyplot as plt
from collections import OrderedDict
from dingtou.pyramid.pyramid_policy import PyramidPolicy
from dingtou.pyramid.pyramid_strategy import PyramidStrategy

logger = logging.getLogger(__name__)

"""
再test_timing基础上做的改进
"""


def backtest(df_baseline: DataFrame,
             funds_data: dict,
             grid_height_dict: dict,
             start_date,
             end_date,
             amount,
             grid_height,
             grid_share):
    # 上来是0元
    broker = Broker(amount)
    broker.set_buy_commission_rate(0.0001)  # 参考华宝证券：ETF手续费万1，单笔最低0.2元
    broker.set_sell_commission_rate(0)
    backtester = BackTester(broker, start_date, end_date)
    policy = PyramidPolicy(grid_share)
    strategy = PyramidStrategy(broker, policy, grid_height_dict)
    backtester.set_strategy(strategy)
    # 单独调用一个set_data，是因为里面要做特殊处理
    backtester.set_data(df_baseline, funds_data)

    # 运行回测！！！
    backtester.run()
    return broker.df_total_market_values, broker


def calculate_metrics(df_portfolio, df_baseline, df_fund, broker):
    def annually_profit(start_value, end_value, start_date, end_date):
        """
        细节：earn是一个百分比，不是收益/投入，而是终值/投入，这个是年化公式要求的，
        所以返回的时候，最终减去了1
        参考：https://www.pynote.net/archives/1667
        :param earn:
        :param broker:
        :return:
        """
        earn = end_value / start_value
        years = relativedelta(dt1=end_date, dt2=start_date).years
        months = relativedelta(dt1=end_date, dt2=start_date).months % 12
        years = years + months / 12
        return earn ** (1 / years) - 1



    # 计算各项指标
    stat = OrderedDict()
    stat["基金代码"] = df_fund.iloc[0].code
    stat["基准指数"] = df_baseline.iloc[0].code
    stat["投资起始"] = df_portfolio.index.min()
    stat["投资结束"] = df_portfolio.index.max()
    stat["定投起始"] = broker.df_trade_history[0].target_date
    stat["定投结束"] = broker.df_trade_history[-1].target_date

    start_value = args.amount
    end_value = broker.get_total_value() - broker.total_commission
    start_date = df_baseline.index.min()
    end_date = df_baseline.index.max()
    stat["期初总资金"] = start_value
    stat["期末现金"] = broker.total_cash
    stat["期末持仓"] = broker.df_total_market_values.iloc[-1].total_position_value
    stat["期末总值"] = broker.get_total_value()
    stat["组合收益"] = end_value - start_value
    stat["组合收益"] = end_value / start_value - 1
    stat["组合年化"] = annually_profit(start_value, end_value, start_date, end_date)


    """
    接下来考察，仅投资用的现金的收益率，不考虑闲置资金了
    """

    # 盈利 = 总卖出现金 + 持有市值 - 总投入现金 - 佣金
    start_value = broker.total_buy_cash
    end_value = broker.total_sell_cash + \
                broker.get_total_position_value() - \
                broker.total_commission
    start_date = broker.df_trade_history[0].target_date
    end_date = broker.df_trade_history[-1].target_date
    stat["总买入资金"] = broker.total_buy_cash
    stat["总卖出资金"] = broker.total_sell_cash
    stat["期末持仓"] = broker.get_total_position_value()
    stat["投资收益"] = end_value - start_value
    stat["投资收益"] = end_value / start_value - 1
    stat["投资年化"] = annually_profit(start_value, end_value, start_date, end_date)
    # 实际投入 = 2*总买入 -  最终市值 - 总卖出，资金利用率就是 = 实际投入/开始的总现金
    actual_buy = 2 * broker.total_buy_cash - broker.get_total_position_value() - broker.total_sell_cash
    stat["资金利用率"] = actual_buy / args.amount

    stat["夏普比率"] = metrics.sharp_ratio(df_portfolio.total_value.pct_change())
    stat["索提诺比率"] = metrics.sortino_ratio(df_portfolio.total_value.pct_change())
    stat["卡玛比率"] = metrics.calmar_ratio(df_portfolio.total_value.pct_change())
    stat["最大回撤"] =metrics.max_drawback(df_portfolio.total_value.pct_change())

    stat["基准收益"] = metrics.total_profit(df_baseline)
    stat["基金收益"] = metrics.total_profit(df_fund)

    stat["买入次数"] = len([t for t in broker.df_trade_history if t.action == 'buy'])
    stat["卖出次数"] = len([t for t in broker.df_trade_history if t.action == 'sell'])
    stat["持仓成本"] = broker.positions[df_fund.iloc[0].code].cost
    stat["当前持仓"] = broker.positions[df_fund.iloc[0].code].position
    stat["当前价格"] = df_fund.iloc[0].close
    stat["佣金总额"] = broker.total_commission

    for k,v in stat.items():
        logger.info("{:>20s} : {}".format(k,v))

    return stat

def plot(df_baseline, df_fund, df_portfolio, df_buy_trades, df_sell_trades):
    code = df_fund.iloc[0].code

    fig = plt.figure(figsize=(50, 10), dpi=(200))

    # 设置基准X轴
    ax_baseline = fig.add_subplot(111)
    ax_baseline.grid()
    ax_baseline.set_title(f"{code}投资报告")
    ax_baseline.set_xlabel('日期')  # 设置x轴标题
    ax_baseline.set_ylabel('基金周线', color='r')  # 设置Y轴标题

    # 设置基准Y轴
    ax_portfolio = ax_baseline.twinx()  # 返回共享x轴的第二个轴
    ax_portfolio.spines['right'].set_position(('outward', 60))  # right, left, top, bottom
    ax_portfolio.set_ylabel('投资组合', color='c')  # 设置Y轴标题

    # 画基准
    # h_baseline_close, = ax_baseline.plot(df_baseline.index, df_baseline.close, 'r')

    # 设置基金Y轴
    ax_fund = ax_baseline.twinx()  # 返回共享x轴的第3个轴
    ax_fund.set_ylabel('基金日线', color='b')  # 设置Y轴标题

    # 画买卖信号
    ax_fund.scatter(df_buy_trades.date, df_buy_trades.price, marker='^', c='r', s=40)
    # 不一定有卖
    if len(df_sell_trades) > 0:
        ax_fund.scatter(df_sell_trades.date, df_sell_trades.price, marker='v', c='g', s=40)

    # 画基金
    h_fund, = ax_fund.plot(df_fund.index, df_fund.close, 'b')
    h_fund_sma, = ax_fund.plot(df_fund.index, df_fund.ma, color='g', linestyle='--', linewidth=0.5)

    # 画组合收益
    h_portfolio, = ax_portfolio.plot(df_portfolio.index, df_portfolio.total_value, 'c')
    # 画成本线
    h_cost, = ax_fund.plot(df_portfolio.index, df_portfolio.cost, 'm', linestyle='--', linewidth=0.5)

    plt.legend(handles=[h_fund, h_fund_sma, h_portfolio, h_cost],
               labels=['基金日线', '基金年线', '投资组合', '成本线'],
               loc='best')

    # 保存图片
    fig.savefig(f"debug/{code}_report.svg", dpi=200, format='svg')


def calculate_grid_height_by_statistics(fund_dict):
    grid_height_dict = {}
    for fund_code, df_fund in fund_dict.items():
        # 乖离率
        df_fund['diff_percent'] = (df_fund.close - df_fund.ma) / df_fund.ma
        positive = df_fund[df_fund.diff_percent > 0].diff_percent.quantile(0.8)
        negative = df_fund[df_fund.diff_percent < 0].diff_percent.quantile(0.2)
        logger.debug("找出基金[%s]和移动均线偏离80%%的收益率边界值为：[%.1f%%~%.1f%%]",
                     df_fund.iloc[0].code,
                     positive*100,
                     negative*100)
        grid_height = max(positive,-negative)/10
        logger.debug("网格高度为：%.2f%%", grid_height*100)
        grid_height_dict[fund_code] = grid_height
    return grid_height_dict

def main(args):
    # 加载基准指数数据（周频），如果没有设，就用基金自己；如果是sh开头，加载指数，否则，当做基金加载
    if args.baseline is None:
        df_baseline = load_fund(fund_code=args.code)
    elif "sh" in args.baseline:
        df_baseline = load_index(index_code=args.baseline)
    else:
        df_baseline = load_fund(fund_code=args.baseline)


    # 加载基金数据，标准化列名，close是为了和标准的指数的close看齐
    fund_dict = load_funds(fund_codes=args.code.split(","),ma_days=args.ma)

    grid_height_dict = calculate_grid_height_by_statistics(fund_dict)

    # 思来想去，还是分开了baseline和funds（支持多只）的数据

    df_portfolio, broker = backtest(
        df_baseline,
        fund_dict,
        grid_height_dict,
        args.start_date,
        args.end_date,
        args.amount,
        args.grid_height,
        args.grid_share)
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
    for fund_code, df_fund in fund_dict.items():
        df_fund = df_fund[(df_fund.index > start_date) & (df_fund.index < end_date)]
        df_portfolio = df_portfolio[(df_portfolio.index > start_date) & (df_portfolio.index < end_date)]

        stat = calculate_metrics(df_portfolio, df_baseline, df_fund, broker)
        df_stat = df_stat.append(stat,ignore_index=True)

        df_buy_trades = DataFrame()
        df_sell_trades = DataFrame()
        for trade in broker.df_trade_history:
            if trade.action == 'buy':
                df_buy_trades = df_buy_trades.append({'date': trade.actual_date, 'price': trade.price}, ignore_index=True)
            else:
                df_sell_trades = df_sell_trades.append({'date': trade.actual_date, 'price': trade.price}, ignore_index=True)

        plot(df_baseline, df_fund, df_portfolio, df_buy_trades, df_sell_trades)

    with pd.option_context('display.max_rows', 100, 'display.max_columns', 100):
        logger.info(df_stat)
    df_stat.to_csv("debug/stat.csv")

"""
指数代码：https://q.stock.sohu.com/cn/zs.shtml
sh000001: 上证指数
sh000300: 沪深300
sh000016：上证50
sh000905：中证500
sh000906：中证800
sh000852：中证1000

python -m dingtou.pyramid.pyramid -c 510500 -s 20180101 -e 20211201 -b sh000905

python -m dingtou.pyramid.pyramid -c 510500 \
-s 20180101 -e 20210101 -b sh000001 \
-a 200000 -gs 2000 -gh 0.02

python -m dingtou.pyramid.pyramid \
-c 510310,510560,512000,512010,512040,512070,512330,512480,512560,512600 \
-s 20180101 -e 20210101 -b sh000001 \
-a 200000 -gs 2000 -gh 0.02



"""
if __name__ == '__main__':
    utils.init_logger()

    # 获得参数
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--start_date', type=str, default="20150101", help="开始日期")
    parser.add_argument('-e', '--end_date', type=str, default="20221201", help="结束日期")
    parser.add_argument('-b', '--baseline', type=str, default=None, help="基准指数，这个策略里就是基金本身")
    parser.add_argument('-m', '--ma', type=int, default=4, help="基金的移动均值")
    parser.add_argument('-c', '--code', type=str, help="股票代码")
    parser.add_argument('-a', '--amount', type=int, default=500000, help="投资金额，默认50万")
    parser.add_argument('-gs', '--grid_share', type=int, default=10000, help="每网格买入份数，默认1万")
    parser.add_argument('-gh', '--grid_height', type=float, default=0.02, help="网格高度,默认2%")
    args = parser.parse_args()

    main(args)
