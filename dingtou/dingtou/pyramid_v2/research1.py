import argparse
import datetime
import time
import logging
import pandas as pd
from pandas import DataFrame
from tabulate import tabulate

from dingtou.pyramid_v2.pyramid_v2 import main
from dingtou.utils import utils
from dingtou.utils.utils import parallel_run, split_periods, AttributeDict, date2str, str2date

CORE_NUM = 16

logger = logging.getLogger(__name__)


def backtest(period, code):
    start_date = period[0]
    end_date = period[1]
    args = AttributeDict()
    args.start_date = start_date
    args.end_date = end_date
    args.amount = 200000  # 20万
    args.baseline = 'sh000001'
    args.ma = -480  # 使用回看2年的均线=(最高+最低)/2
    args.code = code
    args.grid_height = 0.01  # 格子高度1%
    args.grid_share = 1000  # 基准是1000份
    args.quantile_positive = 0.5
    args.quantile_negative = 0.5
    df = main(args, plot_file_subfix=f'{code}_{start_date}_{end_date}')
    return df


def run(code, start_date, end_date, years, roll_months):
    """
    测试和优化方案：
    测试周期：  2013.1~2023.1（10年）
    测试窗口    2年、3年、5年
    滚动窗口    3个月，每年4个月
    测试数量：  8x4+7x4+5x4= 32+28+20 = 80个测试（ 剩余年数 * 年移动4次）
    """

    # 从2013~2015年，每隔3个月，向后滚动2、3、5年的一个周期
    ranges = []
    for year in [int(y) for y in args.years.split(",")]:
        ranges += split_periods(start_date=str2date(start_date),
                                end_date=str2date(end_date),
                                window_years=year,
                                roll_stride_months=roll_months)

    # 并行跑
    # debug
    dfs = parallel_run(core_num=CORE_NUM,
                       iterable=ranges,
                       func=backtest,
                       code=code)

    df = pd.concat(dfs)

    df.to_csv(f"debug/{code}_{start_date}_{end_date}_{years}_{roll_months}.csv")


# python -m dingtou.pyramid_v2.research1 -c 510500
if __name__ == '__main__':
    utils.init_logger()
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--start_date', type=str, default="20150101", help="开始日期")
    parser.add_argument('-e', '--end_date', type=str, default="20221201", help="结束日期")
    parser.add_argument('-c', '--code', type=str, help="股票代码")
    parser.add_argument('-y', '--years', type=str, default='2,3,5', help="测试年份")
    parser.add_argument('-r', '--roll', type=int, default=3, help="滚动月份")
    args = parser.parse_args()

    start_time = time.time()
    run(args.code,
        args.start_date,
        args.end_date,
        args.years,
        args.roll)

    logger.debug("耗时: %s ", str(datetime.timedelta(seconds=time.time() - start_time)))
