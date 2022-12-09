import argparse
import logging
from pandas import DataFrame

from dingtou.backtest import utils
from dingtou.backtest.backtester import BackTester
from dingtou.backtest.broker import Broker
from dingtou.backtest.data_loader import load_fund, load_index
from dingtou.grid.grid_strategy import GridStrategy
from dingtou.backtest.utils import date2str, str2date, day2week
from dingtou.backtest import metrics
import matplotlib.pyplot as plt
import mplfinance as mpf


logger = logging.getLogger(__name__)

"""
这个策略的思路是：
- 利用网格策略来，越跌越买，越涨越卖
- 那么网格高度是多少？是基金周频的ATR，所以我生成了周频基金K线
- 越跌越买，这次不用均线了，就是纯粹越跌越买
- 买的仓位是严格按照网格的公式来的，参见grid_strategy.py
- 每天开始的时候，做风控，设了一个10%的风控，整体仓位得到这个就清仓
- 为了防止踏空，设了一个30%的最低持仓，不触发分控，即使涨，也不卖，直到达到30%的仓位

结果，效果非常差，比之前的纯定投，按照大盘或基金的均线下跌买入策略都差，
这个策略的总收益是在20%，纯定投是100%，均线买入是150%，基金本身是250%，
大概是从2017~至今，基金委003095。
"""

def backtest(df_baseline: DataFrame, funds_data: dict, start_date, end_date, amount, sma_periods=None):
    broker = Broker(amount)
    backtester = BackTester(broker, start_date, end_date)
    backtester.set_strategy(GridStrategy(broker, amount))
    # 单独调用一个set_data，是因为里面要做特殊处理
    backtester.set_data(df_baseline, funds_data)

    # 运行回测！！！
    backtester.run()
    return broker


def calculate_metrics(df_portfolio, df_baseline, df_fund, broker):
    # 计算各项指标
    logger.info("\t交易统计：")
    logger.info("\t\t基金代码：%s", df_fund.iloc[0].code)
    logger.info("\t\t基准指数：%s", df_baseline.iloc[0].code)
    logger.info("\t\t投资起始：%r", metrics.scope(df_portfolio))
    logger.info("\t\t定投起始：%r~%r",
                date2str(broker.df_trade_history[0].target_date),
                date2str(broker.df_trade_history[-1].target_date))
    logger.info("\t\t组合收益：%.1f%% \t<---", metrics.total_profit(df_portfolio, key='total_value') * 100)
    logger.info("\t\t组合年化：%.1f%% \t\t<---", metrics.annually_profit(df_portfolio, key='total_value') * 100)
    logger.info("\t\t夏普比率：%.2f",metrics.sharp_ratio(df_portfolio.total_value.pct_change()))
    logger.info("\t\t索提诺比率：%.2f", metrics.sortino_ratio(df_portfolio.total_value.pct_change()))
    logger.info("\t\t卡玛比率：%.2f", metrics.calmar_ratio(df_portfolio.total_value.pct_change()))
    logger.info("\t\t最大回撤：%.2f%%", metrics.max_drawback(df_portfolio.total_value.pct_change())*100)
    logger.info("\t\t基准收益：%.1f%%", metrics.total_profit(df_baseline) * 100)
    logger.info("\t\t基金收益：%.1f%%", metrics.total_profit(df_fund) * 100)
    logger.info("\t\t买入次数：%.0f", len([t for t in broker.df_trade_history if t.action == 'buy']))
    logger.info("\t\t卖出次数：%.0f", len([t for t in broker.df_trade_history if t.action == 'sell']))
    logger.info("\t\t佣金总额：%.2f", broker.total_commission)
    logger.info("\t\t期末现金：%.2f", broker.total_cash)
    logger.info("\t\t期末持仓：%.2f", broker.df_total_market_value.iloc[-1].total_position_value)
    logger.info("\t\t期末总值：%.2f", broker.df_total_market_value.iloc[-1].total_value)

    return df_portfolio


def plot(df_baseline, df_fund, df_portfolio, df_buy_trades, df_sell_trades):
    code = df_fund.iloc[0].code

    fig, ax_baseline = plt.subplots(1, figsize=(50, 10), sharex=True)

    # 设置X轴
    # ax_baseline = fig.add_subplot(111)
    ax_baseline.grid()
    ax_baseline.set_title(f"{code}投资报告")
    # ax_baseline.set_xticks(rotation=45)
    ax_baseline.set_xlabel('日期')  # 设置x轴标题
    ax_baseline.set_ylabel('指数', color='r')  # 设置Y轴标题

    # 设置Y轴
    ax_portfolio = ax_baseline.twinx()  # 返回共享x轴的第二个轴
    ax_portfolio.spines['right'].set_position(('outward', 60))  # right, left, top, bottom
    ax_portfolio.set_ylabel('投资组合', color='c')  # 设置Y轴标题

    # 画指数和均线
    # h_baseline_close, = ax_baseline.plot(df_baseline.index, df_baseline.close, 'r')
    # h_baseline_sma, = ax_baseline.plot(df_baseline.index, df_baseline.sma, color='g', linestyle='--', linewidth=0.5)

    # 设置基金Y轴
    ax_fund = ax_baseline.twinx()
    ax_fund.set_ylabel('基金', color='b')  # 设置Y轴标题
    ax_fund.scatter(df_buy_trades.date, df_buy_trades.price, marker='^', c='r', s=20)
    ax_fund.scatter(df_sell_trades.date, df_sell_trades.price, marker='v', c='g', s=20)

    # 画基金
    # h_fund, = ax_fund.plot(df_fund.index, df_fund.close, 'b')

    # 画组合收益
    h_portfolio, = ax_portfolio.plot(df_portfolio.index, df_portfolio.total_value, 'c')

    plt.legend(handles=[ h_portfolio],
               labels=[ '投资组合'],
               loc='best')

    mc = mpf.make_marketcolors(
        up='red',
        down='green',
        edge='i',
        wick='i',
        volume='in',
        inherit=True)
    s = mpf.make_mpf_style(
        gridaxis='both',
        gridstyle='-.',
        y_on_right=False,
        marketcolors=mc)
    df_fund['high'] = df_fund.close
    df_fund['low'] = df_fund.close
    df_fund['open'] = df_fund.close
    df_fund_week = utils.day2week(df_fund)
    kwargs = dict(
        type='candle',
        volume=False,
        title='基金的走势',
        ylabel='K线',
        ylabel_lower='')#,figratio=(15, 10)
    # mpf.plot(df_fund_week, ax=ax_fund, **kwargs)  # 简单画法
    mpf.plot(df_fund_week, ax=ax_fund, style=s, type='candle', show_nontrading=True)

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

    # 加载基金数据，标准化列名，close是为了和标准的指数的close看齐
    df_fund = load_fund(fund_code=code)

    # # 由日频改为周频，必须是要日期为索引列，这个是day2week函数要求的
    # df_baseline = day2week(df_baseline)
    # df_fund = day2week(df_fund)

    broker = backtest(
        df_baseline,
        {code: df_fund},
        args.start_date,
        args.end_date,
        args.amount)
    df_portfolio = broker.df_total_market_value
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

    # 画图
    df_buy_trades = DataFrame()
    df_sell_trades = DataFrame()
    for trade in broker.df_trade_history:
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



# 以中证500为基准，测试基金grid投资策略
python -m dingtou.grid.grid -c 003095 -s 20180101 -e 20211201 -b sh000905 
"""
if __name__ == '__main__':
    utils.init_logger()

    # 获得参数
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--start_date', type=str, default="20150101", help="开始日期")
    parser.add_argument('-e', '--end_date', type=str, default="20221201", help="结束日期")
    parser.add_argument('-b', '--baseline', type=str, default=None, help="基准指数")
    parser.add_argument('-c', '--code', type=str, help="股票代码")
    parser.add_argument('-a', '--amount', type=int, default=500000, help="投资金额")
    args = parser.parse_args()

    if "," in args.code:
        for code in args.code.split(","):
            main(code)
    else:
        main(args.code)
