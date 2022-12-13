import logging

import matplotlib.dates as mdates
import matplotlib.pyplot as plt

logger = logging.getLogger(__name__)

def plot(df_baseline, df_fund, df_portfolio, df_buy_trades, df_sell_trades, plot_file_subfix):
    plt.clf()
    code = df_fund.iloc[0].code
    fig = plt.figure(figsize=(50, 10), dpi=(200))

    # 设置基准X轴
    ax_baseline = fig.add_subplot(211)
    ax_baseline.grid()
    ax_baseline.set_title(f"{code}投资报告")
    ax_baseline.set_xlabel('日期')  # 设置x轴标题
    ax_baseline.xaxis.set_major_locator( mdates.MonthLocator(interval=1))
    ax_baseline.xaxis.set_major_formatter(mdates.DateFormatter('%Y/%m'))
    ax_baseline.xaxis.set_tick_params(rotation=45)

    # 画基准
    # if df_baseline is not None:
    #     h_baseline_close, = ax_baseline.plot(df_baseline.index, df_baseline.close, 'r')

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

    ###################################################

    ax_baseline = fig.add_subplot(212)
    ax_baseline.grid()
    ax_baseline.set_title(f"{code}投资报告")
    ax_baseline.set_xlabel('日期')  # 设置x轴标题
    ax_baseline.xaxis.set_major_locator( mdates.MonthLocator(interval=1))
    ax_baseline.xaxis.set_major_formatter(mdates.DateFormatter('%Y/%m'))
    ax_baseline.xaxis.set_tick_params(rotation=45)

    # 画组合收益
    h_portfolio, = ax_baseline.plot(df_portfolio.index, df_portfolio.total_value, 'c')
    h_position, = ax_baseline.plot(df_portfolio.index, df_portfolio.total_position_value, 'g')
    h_cash, = ax_baseline.plot(df_portfolio.index, df_portfolio.cash, color='#aaaaaa')
    plt.legend(handles=[h_portfolio, h_position,h_cash],
               labels=['总市值', '持仓', '现金'],
               loc='best')

    # 保存图片
    fig.savefig(f"debug/{code}_report_{plot_file_subfix}.svg", dpi=200, format='svg')

