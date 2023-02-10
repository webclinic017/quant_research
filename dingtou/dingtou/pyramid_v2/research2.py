import argparse
import datetime
import logging
import time

import pandas as pd

from dingtou.pyramid_v2.research1 import run
from dingtou.utils import utils
import itertools
from tqdm import tqdm
logger = logging.getLogger(__name__)
"""
research1基础上，做参数调优
需要调参的参数包括：
- 使用的均线：480
- 使用的网格限度：
    [0.2,0.5],[0.2,0.6],[0.2,0.8],
    [0.4,0.5],[0.4,0.6],[0.4,0.8],
"""
native_quantiles = [0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9]
positive_quantiles = [0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9]

quantiles = list(itertools.product(*[native_quantiles,positive_quantiles]))

MAs = [240, 480, 850, -240, -480]


"""
quantiles = 10x10 = 100
mas = 5
4只基金一次回测：7 s
合计：5x100x7 = 3500 s
16核一起跑：3500/16 = 218 s = 4 minutes
"""

def main(code, start_date, end_date, years, roll_months, cores):
    dfs = []
    pbar = tqdm(total=len(quantiles)*len(MAs))

    i = 1
    for q in quantiles:
        for ma in MAs:
            df_result = run(code, start_date, end_date, ma, q, years, roll_months, cores)
            df_result['负收益分位数'] = q[0]
            df_result['正收益分位数'] = q[1]
            df_result['移动均值'] = ma
            dfs.append(df_result)
            pbar.update(i)
            i+= 1
    df = pd.concat(dfs)
    df.to_csv(f"debug/{code}_{start_date}_{end_date}_{years}_{roll_months}_quantiles.csv")


# python -m dingtou.pyramid_v2.research2 -c 510310,510500,159915,588090 -s 20130101 -e 20230101 -cs 16
# python -m dingtou.pyramid_v2.research2 -c 510310,510500,159915,588090 -s 20180101 -e 20210101 -y 2 -r 6 -cs 2
if __name__ == '__main__':
    utils.init_logger(file=True)
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--start_date', type=str, default="20130101", help="开始日期")
    parser.add_argument('-e', '--end_date', type=str, default="20230101", help="结束日期")
    parser.add_argument('-cs', '--cores', type=int, default=5)
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
