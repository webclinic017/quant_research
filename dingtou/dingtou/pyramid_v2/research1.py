import argparse
import datetime
import logging
import time

import pandas as pd

from dingtou.pyramid_v2.pyramid_v2 import main
from dingtou.utils import utils
from dingtou.utils.multi_processor import execute
from dingtou.utils.utils import split_periods, AttributeDict, str2date

logger = logging.getLogger(__name__)

def backtest(data, code, ma, quantiles, result):
    """
    为了符合我那个multiprocessor并行跑的框架，必须要求，
    第一个参数是迭代的参数，
    第二参数是返回用的数据，
    后面才是真正的参数，必须这么约定
    :param data:
    :param result:
    :param code:
    :param ma:
    :param quantiles:
    :return:
    """

    # 这里data是一个数据组，里面是日期对，如[['20180101', '20200101'],...]
    for period in data:
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
        result.append(df)  # 把结果append到数组里


def run(code, start_date, end_date, ma, quantiles, years, roll_months, cores):
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
    results = execute(data=ranges,
            worker_num=cores,
            function=backtest,
            code=code,
            ma=ma,
            quantiles=quantiles)
    df = pd.concat(results)
    df.to_csv(f"debug/{code}_{start_date}_{end_date}_{years}_{roll_months}.csv")

# python -m dingtou.pyramid_v2.research1 -c 510310,510500,159915,588090 -s 20130101 -e 20230101 -cs 16
# python -m dingtou.pyramid_v2.research1 -c 510500 -s 20180101 -e 20220101 -y 2 -r 6 -cs 2
if __name__ == '__main__':
    utils.init_logger(file=True)
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--start_date', type=str, default="20130101", help="开始日期")
    parser.add_argument('-e', '--end_date', type=str, default="20230101", help="结束日期")
    parser.add_argument('-cs', '--cores', type=int, default=10)
    parser.add_argument('-c', '--code', type=str, help="股票代码")
    parser.add_argument('-y', '--years', type=str, default='2,3,5', help="测试年份")
    parser.add_argument('-r', '--roll', type=int, default=3, help="滚动月份")
    args = parser.parse_args()

    start_time = time.time()
    run(args.code,
        args.start_date,
        args.end_date,
        -480,  # 默认的2年回看最大徐小均线
        [0.2, 0.8],  # 默认的上下边界
        args.years,
        args.roll,
        args.cores)

    logger.debug("耗时: %s ", str(datetime.timedelta(seconds=time.time() - start_time)))
