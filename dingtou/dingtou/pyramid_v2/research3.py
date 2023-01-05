import argparse
import datetime
import math
import time
import logging
import pandas as pd

from dingtou.pyramid_v2.pyramid_v2 import main
from dingtou.pyramid_v2.research1 import run
from dingtou.utils import utils
from dingtou.utils.utils import parallel_run, split_periods, AttributeDict, str2date

logger = logging.getLogger(__name__)

"""
research1基础上，做参数调优
需要调参的参数包括：
- 使用的均线：
    240，480，850
    -240，-480
- 使用的网格限度：
    [0.2,0.6]
"""

quantiles = [0.2, 0.8]
mas = [240, 480, 850, -240, -480]


def main(code, start_date, end_date, years, roll_months, cores):
    dfs = []
    for ma in mas:
        dfs.append(run(code, start_date, end_date, ma, quantiles, years, roll_months, cores))
    df = pd.concat(dfs)
    df.to_csv(f"debug/{code}_{start_date}_{end_date}_{years}_{roll_months}_ma.csv")


# python -m dingtou.pyramid_v2.research2 -c 510310,510500,159915,588090 -s 20130101 -e 20230101 -cs 5
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
    main(args.code,
         args.start_date,
         args.end_date,
         args.years,
         args.roll,
         args.cores)

    logger.debug("耗时: %s ", str(datetime.timedelta(seconds=time.time() - start_time)))
