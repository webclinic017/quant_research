import argparse
import datetime
import itertools
import logging
import time

import pandas as pd

from dingtou.pyramid_v2.pyramid_v2 import main
from dingtou.utils import utils
from dingtou.utils.multi_processor import execute
from dingtou.utils.utils import split_periods, AttributeDict, str2date
import numpy as np
logger = logging.getLogger(__name__)

"""
测试金字塔的买法中，买卖的比例是否有最优？
测试方案，就用[-0.4,0.8]+850+7只表现好的etf，来测试，测试的话，就测试10年了，不在分不同年限了。
买:[1,2,3]
卖:[1,2,3]
组合[[1,1],[1,2],[1,3],[2,1],....]
"""

def backtest(data, code, start_date,end_date, ma, quantiles, result):
    """
    为了符合我那个multiprocessor并行跑的框架，必须要求，
    第一个参数是迭代的参数，
    第二参数是返回用的数据，
    后面才是真正的参数，必须这么约定
    :param data:
    :param result: ----> 是一个固定的list类型，用于返回结果，使用多进程只能这样返回结果
    :param code:
    :param ma:
    :param quantiles:
    :return:
    """

    # 这里data是一个数据组，里面是日期对，如[['20180101', '20200101'],...]
    for factor in data:
        args = AttributeDict()
        args.buy_factor = factor[0]
        args.sell_factor = factor[1]
        args.code = code
        args.start_date = start_date
        args.end_date = end_date
        args.amount = 0  # 0万
        args.baseline = 'sh000001'
        args.ma = ma
        args.code = code
        args.grid_height = 0.01  # 格子高度1%
        args.grid_amount = 1000  # 1个格子是1000元
        args.quantile_negative = quantiles[0]
        args.quantile_positive = quantiles[1]
        args.bank = True # 使用借款方法
        df_stat,df_trade = main(args)
        df_stat['买倍数'] = factor[0]
        df_stat['卖倍数'] = factor[1]
        result.append([df_stat,df_trade])  # 把结果append到数组里


def run(code, start_date, end_date, ma, quantiles, years, roll_months, cores):
    start_time = time.time()

    buy_factors = [1]
    sell_factors = np.linspace(0.5,3,26).tolist()# [0.5, 0.6, 0.7, 0.8, ..., 3]
    factors = list(itertools.product(*[buy_factors, sell_factors]))

    results = execute(data=factors,
            worker_num=cores,
            code = code,
            function=backtest,
            start_date=start_date,
            end_date=end_date,
            ma=ma,
            quantiles=quantiles)
    stats, trades  = zip(*results)
    df_stat = pd.concat(stats)
    df_stat.to_csv(f"debug/stat_buy_sell_factors_{start_date}_{end_date}_{years}_{roll_months}.csv")
    df_trade = pd.concat(trades)
    df_trade.to_csv(f"debug/trade_buy_sell_factors_{start_date}_{end_date}_{years}_{roll_months}.csv")

    logger.debug("完成均值[%.2f],分位数%r,[%s]年，间隔[%d]个月，使用[%d]核的回测，耗时: %s ",
                 ma,
                 quantiles,
                 years,
                 roll_months,
                 cores,
                 str(datetime.timedelta(seconds=time.time() - start_time)))
    return df_stat,df_trade

"""
python -m dingtou.pyramid_v2.research6 -s 20130101 -e 20230101 -cs 16  -m 850 -q 0.4,0.8 -y 10 -c 510500
# 512690,512580,512660,159915,159928,510330,510500
"""
if __name__ == '__main__':
    utils.init_logger(file=True)
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--start_date', type=str, default="20130101", help="开始日期")
    parser.add_argument('-e', '--end_date', type=str, default="20230101", help="结束日期")
    parser.add_argument('-cs', '--cores', type=int, default=16)
    parser.add_argument('-c', '--code', type=str, help="股票代码")
    parser.add_argument('-y', '--years', type=str, default='10', help="测试年份")
    parser.add_argument('-r', '--roll', type=int, default=3, help="滚动月份")
    parser.add_argument('-m', '--ma', type=int, default=850)
    parser.add_argument('-q', '--quantile', type=str, default='0.4,0.8')
    args = parser.parse_args()

    # 测试的
    run(args.code,
        args.start_date,
        args.end_date,
        args.ma,
        [float(q) for q in args.quantile.split(",")],
        args.years,
        args.roll,
        args.cores)

