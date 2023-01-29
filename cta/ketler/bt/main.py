import argparse
import logging
import time

import backtrader as bt
from backtrader_plotting import Bokeh

from ketler.bt.ketler_strategy import KetlerStrategy
from utils import utils, data_loader
from utils.utils import AStockPlotScheme, str2date

logger = logging.getLogger(__name__)


def main(start_date, end_date, code):
    cerebro = bt.Cerebro()

    df = data_loader.load_stock(code)
    data = data_loader.bt_wrapper(df,start_date,end_date)
    cerebro.adddata(data, name=code)

    cerebro.broker.setcash(cash)
    cerebro.broker.setcommission(commission=0.002)
    cerebro.broker.set_slippage_perc(0.000)  # 0%的滑点
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trade')
    cerebro.addstrategy(KetlerStrategy)
    results = cerebro.run(runonce=False)

    pnl = cerebro.broker.get_value() - cash
    stat = {}
    stat['股票代码'] = code
    stat['开始日期'] = start_date
    stat['结束日期'] = end_date
    stat['原始资金'] = cash
    stat['最后资金'] = cerebro.broker.get_value()
    stat['盈利金额'] = pnl
    stat['盈亏比例'] = 100 * pnl / cash
    plot_stat(cerebro, stat, code, start_date, end_date)
    return stat['盈亏比例']


def plot_stat(cerebro, stat, code, start_date, end_date):
    file_name = "debug/{}_{}_{}.html".format(code, start_date, end_date)
    # output_mode='save'
    b = Bokeh(filename=file_name,
              style='bar',
              tabs="single",
              output_mode='show',
              scheme=AStockPlotScheme(),
              show=False)
    cerebro.plot(b, stype='candle')

    # 显示在屏幕上
    for k, v in stat.items():
        print(k, " : ", v)


"""
python -m ketler.bt.main \
    -s 20200101 \
    -e 20220501 \
    -c 300347.SZ
"""
if __name__ == '__main__':
    ##########################
    # 主程序开始
    #########################

    utils.init_logger()

    cash = 100000 # 10万

    start_time = time.time()
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--start', type=str, help="开始日期")
    parser.add_argument('-e', '--end', type=str, help="结束日期")
    parser.add_argument('-c', '--code', type=str, help="code")
    args = parser.parse_args()

    main(str2date(args.start),
         str2date(args.end),
         args.code)
    logger.debug("共耗时: %.0f 秒", time.time() - start_time)
