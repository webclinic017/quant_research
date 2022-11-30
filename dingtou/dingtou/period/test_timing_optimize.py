import argparse
import logging

from dateutil.relativedelta import relativedelta
from pandas import DataFrame

from dingtou.backtest import utils
from dingtou.backtest.backtester import BackTester
from dingtou.backtest.broker import Broker
from dingtou.backtest.data_loader import load_fund, load_index
from dingtou.period.cash_distribution import MAOptimizeCashDistribute
from dingtou.backtest.utils import date2str, str2date, day2week
from dingtou.period.timing_optimize_strategy import TimingOptimizeStrategy
from dingtou.backtest import metrics
import matplotlib.pyplot as plt

logger = logging.getLogger(__name__)

"""
再test_timing基础上做的改进
"""


def backtest(df_baseline: DataFrame, funds_data: dict, start_date, end_date,
             amount, periods, sma_periods,
             profit_percent, sell_percent):
    # 上来是0元
    broker = Broker(0)
    backtester = BackTester(broker, start_date, end_date)
    strategy = TimingOptimizeStrategy(broker,
                                      periods,
                                      MAOptimizeCashDistribute(amount),
                                      sma_periods,
                                      profit_percent,
                                      sell_percent
                                      )
    backtester.set_strategy(strategy)
    # 单独调用一个set_data，是因为里面要做特殊处理
    backtester.set_data(df_baseline, funds_data)

    # 运行回测！！！
    backtester.run()
    return broker.df_values, broker


def calculate_metrics(df_portfolio, df_baseline, df_fund, broker):
    def annually_profit(df, broker):
        earn = (broker.get_total_value() - broker.total_commission) / broker.total_invest
        start_date = df.index.min()
        end_date = df.index.max()
        years = relativedelta(dt1=end_date, dt2=start_date).years
        months = relativedelta(dt1=end_date, dt2=start_date).months % 12
        years = years + months / 12
        return earn ** (1 / years) - 1

    # 计算各项指标
    logger.info("\t交易统计：")
    logger.info("\t\t基金代码：%s", df_fund.iloc[0].code)
    logger.info("\t\t基准指数：%s", df_baseline.iloc[0].code)
    logger.info("\t\t投资起始：%r", metrics.scope(df_portfolio.index.min(), df_portfolio.index.max()))
    logger.info("\t\t定投起始：%r",
                metrics.scope(broker.trade_history[0].target_date, broker.trade_history[-1].target_date))
    logger.info("\t\t组合收益：%.1f元 \t<---",
                broker.get_total_value() - broker.total_commission - broker.total_invest)
    logger.info("\t\t组合收益：%.1f%% \t<---",
                ((broker.get_total_value() - broker.total_commission) / broker.total_invest - 1) * 100)
    logger.info("\t\t组合年化：%.1f%% \t\t<---", annually_profit(df_portfolio, broker) * 100)
    logger.info("\t\t夏普比率：%.2f", metrics.sharp_ratio(df_portfolio.total_value.pct_change()))
    logger.info("\t\t索提诺比率：%.2f", metrics.sortino_ratio(df_portfolio.total_value.pct_change()))
    logger.info("\t\t卡玛比率：%.2f", metrics.calmar_ratio(df_portfolio.total_value.pct_change()))
    logger.info("\t\t最大回撤：%.2f%%", metrics.max_drawback(df_portfolio.total_value.pct_change()) * 100)
    logger.info("\t\t基准收益：%.1f%%", metrics.total_profit(df_baseline) * 100)
    logger.info("\t\t基金收益：%.1f%%", metrics.total_profit(df_fund) * 100)
    logger.info("\t\t买入次数：%.0f", len([t for t in broker.trade_history if t.action == 'buy']))
    logger.info("\t\t卖出次数：%.0f", len([t for t in broker.trade_history if t.action == 'sell']))
    logger.info("\t\t持仓成本：%.2f", broker.positions[df_fund.iloc[0].code].cost)
    logger.info("\t\t当前持仓：%.2f份", broker.positions[df_fund.iloc[0].code].position)
    logger.info("\t\t当前价格：%.2f", df_fund.iloc[0].close)
    logger.info("\t\t佣金总额：%.2f", broker.total_commission)
    logger.info("\t\t总投入本金：%.2f", broker.total_invest)
    logger.info("\t\t期末现金：%.2f", broker.cash)
    logger.info("\t\t期末持仓：%.2f", broker.df_values.iloc[-1].total_position_value)
    logger.info("\t\t期末总值：%.2f", broker.df_values.iloc[-1].total_value)

    return df_portfolio


def plot(df_baseline, df_fund, df_portfolio, df_buy_trades, df_sell_trades):
    code = df_fund.iloc[0].code

    fig = plt.figure(figsize=(50, 10), dpi=(200))

    # 设置X轴
    ax_baseline = fig.add_subplot(111)
    ax_baseline.grid()
    ax_baseline.set_title(f"{code}投资报告")
    # ax_baseline.set_xticks(rotation=45)
    ax_baseline.set_xlabel('日期')  # 设置x轴标题
    ax_baseline.set_ylabel('基金周线', color='r')  # 设置Y轴标题

    # 设置Y轴
    ax_portfolio = ax_baseline.twinx()  # 返回共享x轴的第二个轴
    ax_portfolio.spines['right'].set_position(('outward', 60))  # right, left, top, bottom
    ax_portfolio.set_ylabel('投资组合', color='c')  # 设置Y轴标题

    # 画周线
    h_baseline_close, = ax_baseline.plot(df_baseline.index, df_baseline.close, 'r')
    # 画均线
    h_baseline_sma, = ax_baseline.plot(df_baseline.index, df_baseline.sma, color='g', linestyle='--', linewidth=0.5)

    # 设置基金Y轴
    ax_fund = ax_baseline
    ax_fund.set_ylabel('基金日线', color='b')  # 设置Y轴标题

    # 画买卖信号
    ax_fund.scatter(df_buy_trades.date, df_buy_trades.price, marker='^', c='r', s=40)
    # 不一定有卖
    if len(df_sell_trades) > 0:
        ax_fund.scatter(df_sell_trades.date, df_sell_trades.price, marker='v', c='g', s=40)

    # 画基金
    h_fund, = ax_fund.plot(df_fund.index, df_fund.close, 'b')

    # 画组合收益
    h_portfolio, = ax_portfolio.plot(df_portfolio.index, df_portfolio.total_value, 'c')
    # 画成本线
    h_cost, = ax_fund.plot(df_portfolio.index, df_portfolio.cost, 'm', linestyle='--', linewidth=0.5)

    plt.legend(handles=[h_baseline_close, h_baseline_sma, h_fund, h_portfolio, h_cost],
               labels=['基金周线', '基金N周线均线', '基金日线', '投资组合', '成本线'],
               loc='best')

    # 保存图片
    fig.savefig(f"debug/{code}_report.svg", dpi=200, format='svg')


def main(code):
    # 加载基准指数数据（周频），如果没有设，就用基金自己；如果是sh开头，加载指数，否则，当做基金加载
    if args.baseline is None:
        df_baseline = load_fund(fund_code=code)
    elif "sh" in args.baseline:
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
        args.baseline_sma,
        args.profit_percent,
        args.sell_percent)
    df_portfolio.sort_values('date')
    df_portfolio.set_index('date', inplace=True)

    # 统一过滤一下时间区间,
    # 回测之后再过滤，会担心把start_date之前的也回测了，
    # 不用担心，
    start_date = str2date(args.start_date)
    end_date = str2date(args.end_date)
    df_baseline = df_baseline[(df_baseline.index > start_date) & (df_baseline.index < end_date)]
    df_fund = df_fund[(df_fund.index > start_date) & (df_fund.index < end_date)]
    df_portfolio = df_portfolio[(df_portfolio.index > start_date) & (df_portfolio.index < end_date)]

    calculate_metrics(df_portfolio, df_baseline, df_fund, broker)

    df_buy_trades = DataFrame()
    df_sell_trades = DataFrame()
    for trade in broker.trade_history:
        if trade.action == 'buy':
            df_buy_trades = df_buy_trades.append({'date': trade.actual_date, 'price': trade.price}, ignore_index=True)
        else:
            df_sell_trades = df_sell_trades.append({'date': trade.actual_date, 'price': trade.price}, ignore_index=True)

    plot(df_baseline, df_fund, df_portfolio, df_buy_trades, df_sell_trades)


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




# 以基金自己作为基准，测试基金定投，以基金月均线做择时(4周)
python -m dingtou.period.test_timing_optimize -c 003095 -s 20180101 -e 20211201
"""
if __name__ == '__main__':
    utils.init_logger()

    # 获得参数
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--start_date', type=str, default="20150101", help="开始日期")
    parser.add_argument('-e', '--end_date', type=str, default="20221201", help="结束日期")
    parser.add_argument('-b', '--baseline', type=str, default=None, help="基准指数，这个策略里就是基金本身")
    parser.add_argument('-bma', '--baseline_sma', type=int, default=4, help="基准指数的移动均值周期数（目前是月线）")
    parser.add_argument('-c', '--code', type=str, help="股票代码")
    parser.add_argument('-a', '--amount', type=int, default=20000, help="每次投资金额")
    parser.add_argument('-p', '--periods', type=int, default=150, help="投资期数（150周=3年）")
    parser.add_argument('-sp', '--sell_percent', type=float, default=0.1, help="每次止盈卖出比例")
    parser.add_argument('-pp', '--profit_percent', type=float, default=0.1, help="每次止盈的收益率")
    args = parser.parse_args()

    if "," in args.code:
        for code in args.code.split(","):
            main(code)
    else:
        main(args.code)
