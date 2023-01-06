import argparse
import datetime
import math
import time
import logging
import pandas as pd

from dingtou.pyramid_v2.pyramid_v2 import main
from dingtou.utils import utils
from dingtou.utils.utils import parallel_run, split_periods, AttributeDict, str2date

logger = logging.getLogger(__name__)

TASKS_PER_CORE = 4 # 每个核跑4个，就退出

def backtest(period, code, ma, quantiles):
    start_date = period[0]
    end_date = period[1]
    args = AttributeDict()
    args.start_date = start_date
    args.end_date = end_date
    args.amount = 0  # 0万
    args.baseline = 'sh000001'
    args.ma = ma
    args.code = code
    args.grid_height = 0.01  # 格子高度1%
    args.grid_share = 1000  # 基准是1000份
    args.quantile_negative = quantiles[0]
    args.quantile_positive = quantiles[1]
    args.bank = True
    df = main(args)
    return df


def run(code, start_date, end_date, ma, quantiles,years, roll_months,cores):
    """
    测试和优化方案：
    测试周期：  2013.1~2023.1（10年）
    测试窗口    2年、3年、5年
    滚动窗口    3个月，每年4个月
    测试数量：  8x4+7x4+5x4= 32+28+20 = 80个测试（ 剩余年数 * 年移动4次）
    """

    # 从2013~2015年，每隔3个月，向后滚动2、3、5年的一个周期
    ranges = []
    for year in [int(y) for y in years.split(",")]:
        ranges += split_periods(start_date=str2date(start_date),
                                end_date=str2date(end_date),
                                window_years=year,
                                roll_stride_months=roll_months)

    # 2013.1.1~2023.1.1, 2,3,5年，滚动3个月，合计83个组合
    logger.debug("从%s~%s,分别测试周期为%s的滚动%d个月的组合，合计%d个",start_date,end_date,years,roll_months,len(ranges))

    """
    需要权衡：总内存，1个进程的内存，10个进程，1次700M，3次2.1G，32G，12个CPU比较合适：12x2.1G=24G，在安全之内
    # 如果直接用dask跑，我一共有20个cpu，一起跑，就总会进程崩掉，观察是内存不断在增加导致的，
    # 平均一个python进程跑到5个左右就完蛋，所以控制每个core一口气跑5个组合，还是使用16个core，5个之后，就完事，省的这个进程爆掉，
    # 16个核心，每个核心5个（TASKS_PER_CORE），所以，就是一个批次跑80个
    """
    dfs = []
    # ranges/cores*3, range=83, cores=5, 80/15 = 6
    dask_task_num = cores * TASKS_PER_CORE
    counter = math.ceil(len(ranges) / dask_task_num)
    logger.debug("经过%d轮，每轮使用%d个核，每个核运行%d个任务，每轮合计%d个任务，一共%d个任务",
                 counter,cores,dask_task_num,dask_task_num,len(ranges))
    for i in range(counter):
        r = ranges[i*dask_task_num:(i+1)*dask_task_num]
        dfs = parallel_run(core_num=cores,
                       iterable=r,
                       func=backtest,
                       code=code,
                       ma=ma,
                       quantiles=quantiles)
        logger.debug("完成第%d轮的任务",i+1)
    df = pd.concat(dfs)

    df.to_csv(f"debug/{code}_{start_date}_{end_date}_{years}_{roll_months}.csv")
    return df


# python -m dingtou.pyramid_v2.research1 -c 510310,510500,159915,588090 -s 20130101 -e 20230101 -cs 16
# python -m dingtou.pyramid_v2.research1 -c 510500 -s 20180101 -e 20200101 -y 2 -r 12
if __name__ == '__main__':
    utils.init_logger()
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--start_date', type=str, default="20130101", help="开始日期")
    parser.add_argument('-e', '--end_date', type=str, default="20230101", help="结束日期")
    parser.add_argument('-cs', '--cores', type=int, default=16)
    parser.add_argument('-c', '--code', type=str, help="股票代码")
    parser.add_argument('-y', '--years', type=str, default='2,3,5', help="测试年份")
    parser.add_argument('-r', '--roll', type=int, default=3, help="滚动月份")
    args = parser.parse_args()

    start_time = time.time()
    run(args.code,
        args.start_date,
        args.end_date,
        -480, # 默认的2年回看最大徐小均线
        [0.2,0.8], # 默认的上下边界
        args.years,
        args.roll,
        args.cores)

    logger.debug("耗时: %s ", str(datetime.timedelta(seconds=time.time() - start_time)))
