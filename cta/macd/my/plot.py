import logging

import matplotlib.dates as mdates
import matplotlib.pyplot as plt

from pandas.plotting import table

from utils.utils import date2str
import mplfinance as mpf

logger = logging.getLogger(__name__)

mc = mpf.make_marketcolors(
    up='red',
    down='green',
    edge='i',
    wick='i',
    volume='in',
    inherit=True)
style = mpf.make_mpf_style(
    gridaxis='both',
    gridstyle='-.',
    y_on_right=False,
    marketcolors=mc)
kwargs = dict(
    type='candle',
    volume=False,
    title='基金的走势',
    ylabel='K线',
    ylabel_lower='')  # ,figratio=(15, 10)


def plot(start_date, end_date, broker, df_baseline, df_portfolio, df_dict, df_stat):
    """
    画总图:
    - 总的投资收益图

    :param df_baseline:
    :param df_portfolio:
    :param plot_file_subfix:
    :return:
    """

    plt.clf()

    # 10年是300宽度（目测），2400个交易日240个宽度，
    width = int(len(df_baseline) / 10)
    fig = plt.figure(figsize=(width, 100))  # 8 + 5 * len(df_stat)))
    # fig.set_figheight()
    row = 4  # + len(df_dict)
    col = 1
    pos = 1

    if len(df_stat) > 0:
        ax_table = fig.add_subplot(row, col, pos)
        fig.patch.set_visible(False)
        ax_table.axis('off')
        ax_table.axis('tight')
        table(ax_table, df_stat, loc='center')
        pos += 1

    ################ 画第一张图 ################
    # 设置基准X轴
    ax_baseline = fig.add_subplot(row, col, pos)
    ax_baseline.grid()
    ax_baseline.set_title(f"基准指数K线、收益变动情况")
    ax_baseline.set_xlabel('日期')  # 设置x轴标题
    ax_baseline.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    ax_baseline.xaxis.set_major_formatter(mdates.DateFormatter('%Y/%m'))
    ax_baseline.xaxis.set_tick_params(rotation=45)

    # 画基准,上证指数
    # h_baseline, = ax_baseline.plot(df_baseline.index, df_baseline.close, 'r')
    mpf.plot(df_baseline, ax=ax_baseline, style=style, type='candle', show_nontrading=True)
    ax_baseline.set_ylabel(f'基准{df_baseline.iloc[0].code}', color='r')  # 设置Y轴标题
    ax_portfolio = ax_baseline.twinx()  # 返回共享x轴的第3个轴
    h_portfolio, = ax_portfolio.plot(df_portfolio.index, df_portfolio.total_value, 'c')
    ax_portfolio.set_ylabel(f'组合投资的总市值', color='c')  # 设置Y轴标题
    ax_portfolio.spines['right'].set_position(('outward', 60))  # right, left, top, bottom
    # 画北上资金流
    # df_moneyflow = df_dict['moneyflow']
    # ax_moneyflow = ax_baseline.twinx()  # 返回共享x轴的第3个轴
    # ax_moneyflow.set_ylabel('北上资金', color='r')  # 设置Y轴标题
    # ax_moneyflow.spines['right'].set_position(('outward', 120))  # right, left, top, bottom
    # h_moneyflow, = ax_moneyflow.plot(df_moneyflow.index, df_moneyflow.north_money, 'r')
    # # 画开仓信号
    # df_open = df_moneyflow_position[df_moneyflow_position.position == 'open']
    # ax_moneyflow.scatter(df_open.date, df_open.north_money, marker='^', c='r', s=40)
    # # 画清仓信号
    # df_close = df_moneyflow_position[df_moneyflow_position.position == 'close']
    # ax_moneyflow.scatter(df_close.date, df_close.north_money, marker='v', c='g', s=40)
    # 画出北上资金上下规定的边界区域
    # ax_moneyflow.fill_between(df_moneyflow.index, df_moneyflow.upper, df_moneyflow.lower, alpha=0.2)
    # 画图例
    plt.legend(handles=[h_portfolio],
               labels=['组合投资的总市值'],
               loc='best')

    ################ 画第二张图 ################
    # 画：'总市值', '持仓', '现金'

    pos += 1
    ax_baseline = fig.add_subplot(row, col, pos)
    ax_baseline.grid()
    ax_baseline.set_title(f"总现金、持仓、组合投资的总市值报告")
    ax_baseline.set_xlabel('日期')  # 设置x轴标题
    ax_baseline.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    ax_baseline.xaxis.set_major_formatter(mdates.DateFormatter('%Y/%m'))
    ax_baseline.xaxis.set_tick_params(rotation=45)

    # 画组合收益
    h_position, = ax_baseline.plot(df_portfolio.index, df_portfolio.total_position_value, 'g')
    h_cash, = ax_baseline.plot(df_portfolio.index, df_portfolio.cash, color='#aaaaaa')
    h_portfolio, = ax_baseline.plot(df_portfolio.index, df_portfolio.total_value, 'c', linewidth=2)
    ax_baseline.fill_between(df_portfolio.index, df_portfolio.total_value, 0, alpha=0.1)
    plt.legend(handles=[h_portfolio, h_position, h_cash],
               labels=['组合投资的总市值', '持仓', '现金'],
               loc='best')

    # 画出每只基金的持仓情况
    for code, df_data in df_dict.items():

        # 只过滤回测期间的数据
        df_data = df_data[(df_data.index > start_date) & (df_data.index < end_date)]
        df_portfolio = df_portfolio[(df_portfolio.index > start_date) & (df_portfolio.index < end_date)]

        if len(df_data) == 0:
            logger.warning("基金[%s] 在%s~%s没有数据", code, date2str(start_date), date2str(end_date))
            continue

        if len(broker.df_trade_history) == 0:
            logger.warning("基金[%s] 在%s~%s未发生任何一笔交易", code, date2str(start_date), date2str(end_date))
            continue

        df_buy_trades = broker.df_trade_history[
            (broker.df_trade_history.code == code) & (broker.df_trade_history.action == 'buy')]
        df_sell_trades = broker.df_trade_history[
            (broker.df_trade_history.code == code) & (broker.df_trade_history.action == 'sell')]
        df_data_market = broker.market_value_dict.get(code, None)
        if df_data_market is None:
            # logger.warning("基金[%s] 在%s~%s未发生交易市值变化", code, date2str(start_date), date2str(end_date))
            continue

        pos += 1

        # 画一直基金的信息
        plot_stock(fig, row, col, pos, df_data, df_data_market, df_buy_trades, df_sell_trades)

    # 保存图片
    fig.tight_layout()
    codes = "_".join([k for k, v in df_dict.items()])[:100]
    fig.savefig(f"debug/report_{date2str(start_date)}_{date2str(end_date)}_{codes}.svg", dpi=200, format='svg')
    # 释放内存
    plt.close()


def plot_stock(fig, row, col, pos, df_data, df_data_market_value, df_buy_trades, df_sell_trades):
    """
    :param fig:
    :param row:
    :param col:
    :param pos:
    :param df_data:
    :param df_data_market_value:  投资这只基金的市值变化信息
            df_data_market_value.append({'date': date,
                 'position_value': fund_position_value,  # 市值
                 'position': position,  # 持仓
                 'cost': cost}, ignore_index=True)  # 成本
    :param df_buy_trades: 买这只基金的交易信息
    :param df_sell_trades:
    :return:
    """

    code = df_data.iloc[0].code

    # 设置基准X轴
    ax = fig.add_subplot(row, col, pos)
    ax.grid()
    ax.set_title(f"{code}基金投资")
    ax.set_xlabel('日期')  # 设置x轴标题
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y/%m'))
    ax.xaxis.set_tick_params(rotation=45)

    # 画累计净值基金日线
    ax_fund_accumulate = ax.twinx()  # 返回共享x轴的第3个轴
    ax_fund_accumulate.set_ylabel('累计净值', color='g')  # 设置Y轴标题
    ax_fund_accumulate.spines['right'].set_position(('outward', 60))  # right, left, top, bottom
    # h_fund_accumulate, = ax_fund_accumulate.plot(df_data.index, df_data.close, 'b', linewidth=2)

    # https://blog.csdn.net/wuwei_201/article/details/108018343
    hist_pos = df_data.macd_hist.apply(lambda x: 0 if x <= 0 else x)
    hist_minus = df_data.macd_hist.apply(lambda x: 0 if x > 0 else x)
    add_plot = [
        mpf.make_addplot(hist_pos * 10,
                         type='bar',
                         width=0.7,
                         panel=2,
                         color='red',
                         alpha=1,
                         secondary_y=False,
                         ax=ax_fund_accumulate),
        mpf.make_addplot(hist_minus * 10,
                         type='bar',
                         width=0.7,
                         panel=2,
                         color='green',
                         alpha=1,
                         secondary_y=False,
                         ax=ax_fund_accumulate),
        mpf.make_addplot(df_data.macd, panel=2, color='fuchsia', secondary_y=True, ax=ax_fund_accumulate),
        # mpf.make_addplot(df_data.macd_signal, panel=2, color='b', secondary_y=True, ax=ax_fund_accumulate),

        mpf.make_addplot(df_data.ma5, panel=1, color='b', width=0.5, alpha=0.5, secondary_y=True,
                         ax=ax_fund_accumulate),
        mpf.make_addplot(df_data.ma10, panel=1, color='b', width=1, alpha=0.5, secondary_y=True,
                         ax=ax_fund_accumulate),
        mpf.make_addplot(df_data.ma20, panel=1, color='b', width=2, alpha=0.5, secondary_y=True,
                         ax=ax_fund_accumulate),
    ]
    mpf.plot(df_data,
             ax=ax_fund_accumulate,
             style=style,
             addplot=add_plot,
             type='candle',
             main_panel=0,
             volume_panel=2,
             show_nontrading=True)

    # 画买卖信号
    ax_fund_accumulate.scatter(df_buy_trades.actual_date, df_buy_trades.price * 1.1, marker='^', c='r', s=40)

    # 不一定有卖
    if len(df_sell_trades) > 0:
        ax_fund_accumulate.scatter(df_sell_trades.actual_date, df_sell_trades.price * 1.1, marker='v', c='g', s=40)

    # 画仓位价值变化
    ax_position_value = ax.twinx()  # 返回共享x轴的第二个轴
    ax_position_value.spines['right'].set_position(('outward', 180))  # right, left, top, bottom
    ax_position_value.set_ylabel('持仓价值变化', color='g')  # 设置Y轴标题
    ax_position_value.plot(df_data_market_value.date, df_data_market_value.position_value, 'c')
