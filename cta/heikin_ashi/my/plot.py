import logging

import matplotlib.dates as mdates
import matplotlib.pyplot as plt

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
    plt.clf()

    # 10年是300宽度（目测），2400个交易日240个宽度，
    width = int(len(df_baseline) / 15)
    fig = plt.figure(figsize=(width, 50))  # 8 + 5 * len(df_stat)))
    row = 5
    col = 1
    pos = 1

    ################ 画第一张图 ################
    # 设置基准X轴
    ax_baseline = fig.add_subplot(row, col, pos)
    ax_baseline.grid()
    ax_baseline.set_title(f"基准指数K线、收益变动情况")
    ax_baseline.set_xlabel('日期')  # 设置x轴标题
    ax_baseline.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO, interval=1))
    ax_baseline.xaxis.set_major_formatter(mdates.DateFormatter('%Y/%m/%d'))
    ax_baseline.xaxis.set_tick_params(rotation=45)

    # 画基准,上证指数
    # h_baseline, = ax_baseline.plot(df_baseline.index, df_baseline.close, 'r')
    mpf.plot(df_baseline, ax=ax_baseline, style=style, type='candle', show_nontrading=True)
    ax_baseline.set_ylabel(f'基准{df_baseline.iloc[0].code}', color='r')  # 设置Y轴标题
    ax_portfolio = ax_baseline.twinx()  # 返回共享x轴的第3个轴
    h_portfolio, = ax_portfolio.plot(df_portfolio.index, df_portfolio.total_value, 'c')
    ax_portfolio.set_ylabel(f'组合投资的总市值', color='c')  # 设置Y轴标题
    ax_portfolio.spines['right'].set_position(('outward', 60))  # right, left, top, bottom

    # 画图例
    plt.legend(handles=[h_portfolio],
               labels=['组合投资的总市值'],
               loc='best')

    ################ 画第二张图 ################
    # 画：'总市值', '持仓', '现金'

    pos += 1
    print(row, col, pos)
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

    ################ 画第三张图 ################
    # 画出每只基金的持仓情况
    for code, df_data in df_dict.items():

        # 只过滤回测期间的数据
        df_data = df_data[(df_data.index > start_date) & (df_data.index < end_date)]
        df_portfolio = df_portfolio[(df_portfolio.index > start_date) & (df_portfolio.index < end_date)]

        if len(df_data) == 0:
            logger.warning("基金[%s] 在%s~%s没有数据", code, date2str(start_date), date2str(end_date))
            continue

        # 画普通K线
        pos += 1
        plot_stock(fig, row, col, pos, df_data, broker, code)

        # 画平均K线
        pos += 1
        df_data = df_data[['h_open', 'h_close', 'h_high', 'h_low', 'volume','ema3','ema8','ema17']]
        # 为了让mplfinance画图，要把列名改了
        df_data = df_data.rename(columns={'h_open': 'open',
                                          'h_close': 'close',
                                          'h_high': 'high',
                                          'h_low': 'low'})
        plot_stock(fig, row, col, pos, df_data, broker, code)

    # 保存图片
    fig.tight_layout()
    codes = "_".join([k for k, v in df_dict.items()])[:100]
    fig.savefig(f"debug/report_{date2str(start_date)}_{date2str(end_date)}_{codes}.svg", dpi=200, format='svg')
    # 释放内存
    plt.close()


def get_trades_marketvalues(broker, code):
    if len(broker.df_trade_history) == 0:
        return None, None, None
    df_buy_trades = broker.df_trade_history[
        (broker.df_trade_history.code == code) & (broker.df_trade_history.action == 'buy')]
    df_sell_trades = broker.df_trade_history[
        (broker.df_trade_history.code == code) & (broker.df_trade_history.action == 'sell')]
    df_data_market = broker.market_value_dict.get(code, None)
    return df_buy_trades, df_sell_trades, df_data_market


def plot_stock(fig, row, col, pos, df_data, broker, code):
    df_buy_trades, df_sell_trades, df_data_market = get_trades_marketvalues(broker, code)

    # 设置基准X轴
    ax = fig.add_subplot(row, col, pos)
    ax.grid()
    ax.set_title(f"{code}基金投资")
    ax.set_xlabel('日期')  # 设置x轴标题
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO, interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y/%m/%d'))
    ax.xaxis.set_tick_params(rotation=45)
    mpf.plot(df_data,
             ax=ax,
             style=style,
             type='candle',
             main_panel=0,
             volume_panel=2,
             show_nontrading=True)
    ax.plot(df_data.index, df_data.ema3, color='g', linewidth=0.5)
    ax.plot(df_data.index, df_data.ema8, color='b', linewidth=0.75)
    # color:https://pythondatascience.plavox.info/wp-content/uploads/2016/06/colorpalette.png
    ax.plot(df_data.index, df_data.ema17, color='peru', linewidth=1)

    if df_buy_trades is not None:
        # 画买卖信号
        ax.scatter(df_buy_trades.actual_date, df_buy_trades.price * 1.1, marker='^', c='r', s=40)

        # 不一定有卖
        if len(df_sell_trades) > 0:
            ax.scatter(df_sell_trades.actual_date, df_sell_trades.price * 1.1, marker='v', c='g', s=40)

        # 画仓位价值变化
        # ax_position_value = ax.twinx()  # 返回共享x轴的第二个轴
        # ax_position_value.spines['right'].set_position(('outward', 180))  # right, left, top, bottom
        # ax_position_value.set_ylabel('持仓价值变化', color='g')  # 设置Y轴标题
        # ax_position_value.plot(df_data_market.date, df_data_market.position_value, 'c')
