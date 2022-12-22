import logging

import matplotlib.dates as mdates
import matplotlib.pyplot as plt

from pandas.plotting import table
logger = logging.getLogger(__name__)


def plot(start_date, end_date, broker, df_baseline, df_portfolio, fund_dict, plot_file_subfix, df_stat):
    """
    画总图:
    - 总的投资收益图

    :param df_baseline:
    :param df_portfolio:
    :param plot_file_subfix:
    :return:
    """

    plt.clf()

    fig = plt.figure(figsize=(50, 20), dpi=(200))
    # fig.set_figheight()
    row = 3 + len(fund_dict)
    col = 1
    pos = 1

    if len(df_stat)>0:
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
    ax_baseline.set_title(f"投资收益报告")
    ax_baseline.set_xlabel('日期')  # 设置x轴标题
    ax_baseline.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    ax_baseline.xaxis.set_major_formatter(mdates.DateFormatter('%Y/%m'))
    ax_baseline.xaxis.set_tick_params(rotation=45)

    # 画基准
    h_baseline, = ax_baseline.plot(df_baseline.index, df_baseline.close, 'r')
    ax_baseline.set_ylabel(f'基准{df_baseline.iloc[0].code}', color='r')  # 设置Y轴标题
    ax_portfolio = ax_baseline.twinx()  # 返回共享x轴的第3个轴
    h_portfolio, = ax_portfolio.plot(df_portfolio.index, df_portfolio.total_value, 'c')
    ax_portfolio.set_ylabel(f'组合投资的总市值', color='r')  # 设置Y轴标题
    plt.legend(handles=[h_portfolio, h_baseline],
               labels=['组合投资的总市值', f'基准{df_baseline.iloc[0].code}'],
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
    h_portfolio, = ax_baseline.plot(df_portfolio.index, df_portfolio.total_value, 'c')
    h_position, = ax_baseline.plot(df_portfolio.index, df_portfolio.total_position_value, 'g')
    h_cash, = ax_baseline.plot(df_portfolio.index, df_portfolio.cash, color='#aaaaaa')
    plt.legend(handles=[h_portfolio, h_position, h_cash],
               labels=['组合投资的总市值', '持仓', '现金'],
               loc='best')

    # 画出每只基金的持仓情况
    for code, df_fund in fund_dict.items():

        pos += 1

        # 只过滤回测期间的数据
        df_fund = df_fund[(df_fund.index > start_date) & (df_fund.index < end_date)]
        df_portfolio = df_portfolio[(df_portfolio.index > start_date) & (df_portfolio.index < end_date)]

        if len(broker.df_trade_history)==0:
            logger.warning("基金[%s]未发生任何一笔交易", df_fund.iloc[0].code)
            continue

        df_buy_trades = broker.df_trade_history[
            (broker.df_trade_history.code == code) & (broker.df_trade_history.action == 'buy')]
        df_sell_trades = broker.df_trade_history[
            (broker.df_trade_history.code == code) & (broker.df_trade_history.action == 'sell')]
        df_fund_market = broker.fund_market_dict[code]

        # 画一直基金的信息
        plot_fund(fig, row, col, pos, df_fund, df_fund_market, df_buy_trades, df_sell_trades)

    # 保存图片
    fig.tight_layout()
    fig.savefig(f"debug/report_{plot_file_subfix}.svg", dpi=200, format='svg')


def plot_fund(fig, row, col, pos, df_fund, df_fund_market_value, df_buy_trades, df_sell_trades):
    """
    :param fig:
    :param row:
    :param col:
    :param pos:
    :param df_fund:
    :param df_fund_market_value:  投资这只基金的市值变化信息
            df_fund_market_value.append({'date': date,
                 'position_value': fund_position_value,  # 市值
                 'position': position,  # 持仓
                 'cost': cost}, ignore_index=True)  # 成本
    :param df_buy_trades: 买这只基金的交易信息
    :param df_sell_trades:
    :return:
    """

    code = df_fund.iloc[0].code

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
    h_fund_accumulate, = ax_fund_accumulate.plot(df_fund.index, df_fund.close, 'b', linewidth=2)
    # 画累计净值基金均线
    h_fund_sma, = ax_fund_accumulate.plot(df_fund.index, df_fund.ma, color='#6495ED', linestyle='--', linewidth=1)
    # 额外画一个年线，来参考用
    if 'ma242' in df_fund.columns:
        ax_fund_accumulate.plot(df_fund.index, df_fund.ma242, color='#7FFFAA', linestyle='--', linewidth=0.5)
    # 画买卖信号
    ax_fund_accumulate.scatter(df_buy_trades.actual_date, df_buy_trades.price, marker='^', c='r', s=40)
    # 不一定有卖
    if len(df_sell_trades) > 0:
        ax_fund_accumulate.scatter(df_sell_trades.actual_date, df_sell_trades.price, marker='v', c='g', s=40)
    # 画成我持仓成本线

    h_cost, = ax_fund_accumulate.plot(df_fund_market_value.date, df_fund_market_value.cost, 'm', linestyle='--',
                                      linewidth=0.5)
    """
        :param df_fund_market_value:  投资这只基金的市值变化信息
                df_fund_market_value.append({'date': date,
                     'position_value': fund_position_value,  # 市值
                     'position': position,  # 持仓
                     'cost': cost}, ignore_index=True)  # 成本
    
    """

    # 画仓位数量变化
    ax_position = ax.twinx()  # 返回共享x轴的第二个轴
    ax_position.spines['right'].set_position(('outward', 120))  # right, left, top, bottom
    ax_position.set_ylabel('持仓数量变化', color='g')  # 设置Y轴标题
    h_position, = ax_position.plot(df_fund_market_value.date, df_fund_market_value.position, 'g',linewidth=0.5)

    # 画仓位价值变化
    ax_position_value = ax.twinx()  # 返回共享x轴的第二个轴
    ax_position_value.spines['right'].set_position(('outward', 180))  # right, left, top, bottom
    ax_position_value.set_ylabel('持仓价值变化', color='g')  # 设置Y轴标题
    h_position_value, = ax_position_value.plot(df_fund_market_value.date, df_fund_market_value.position_value, 'c')

    plt.legend(handles=[h_cost, h_fund_accumulate, h_fund_sma, h_position, h_position_value],
               labels=['成本线', f'基金{code}累计净值', '累计净值均线', '持仓份数', '持仓市值'],
               loc='best')
