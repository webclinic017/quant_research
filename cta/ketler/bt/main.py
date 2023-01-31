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

    # 准备股票数据
    df = data_loader.load_stock(code)
    # 把dataframe数据包装成backtrader需要的格式
    data = data_loader.bt_wrapper(df,start_date,end_date)

    # 准备backtrader的核心"脑波"
    cerebro = bt.Cerebro()
    # 灌入数据到导尿包
    cerebro.adddata(data, name=code)
    # 设置起始现金数量
    cerebro.broker.setcash(cash)
    # 设置佣金
    cerebro.broker.setcommission(commission=0.001)# 买卖各千一，合计千二
    # 设置观点
    cerebro.broker.set_slippage_perc(0.000)  # 0%的滑点
    # 设置投资收益分析器
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trade')
    # 加载策略！这步是核心
    cerebro.addstrategy(KetlerStrategy)
    # 运行策略
    results = cerebro.run(runonce=False)

    # 计算和打印各项投资指标
    pnl = cerebro.broker.get_value() - cash
    stat = {}
    stat['股票代码'] = code
    stat['开始日期'] = start_date
    stat['结束日期'] = end_date
    stat['原始资金'] = cash
    stat['最后资金'] = cerebro.broker.get_value()
    stat['盈利金额'] = pnl
    stat['盈亏比例'] = 100 * pnl / cash
    # 画图
    plot_stat(cerebro, stat, code, start_date, end_date)
    return stat['盈亏比例']


def plot_stat(cerebro, stat, code, start_date, end_date):
    file_name = "debug/{}_{}_{}.html".format(code, start_date, end_date)
    # output_mode='save'
    # 使用Bokeh生成HTML的投资图表
    b = Bokeh(filename=file_name,
              style='bar',
              tabs="single",
              output_mode='show',
              scheme=AStockPlotScheme(),# A股的红赚绿赔的bar的显示scheme
              show=False)
    cerebro.plot(b, stype='candle') # 画蜡烛图

    # 显示在屏幕上
    for k, v in stat.items():
        print(k, " : ", v)


"""
python -m ketler.bt.main \
    -s 20200101 \
    -e 20220501 \
    -c 300347.SZ

# 为了和my（我自定义的）回测框架比较，把测试日期提前1个月
python -m ketler.bt.main \
    -s 20191201 \
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
