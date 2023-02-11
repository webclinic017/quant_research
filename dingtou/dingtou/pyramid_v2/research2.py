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
# 全量版
native_quantiles = [0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9]
positive_quantiles = [0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9]
quantiles = list(itertools.product(*[native_quantiles,positive_quantiles]))
MAs = [240, 480, 850, -240, -480]

# 中间版
native_quantiles = [0.2,0.3,0.4,0.5]
positive_quantiles = [0.5,0.6,0.7,0.8]
quantiles = list(itertools.product(*[native_quantiles,positive_quantiles]))
MAs = [240, 480, 850]

# 精简版，正负阈值少一些，MA少一些
native_quantiles = [0.2,0.3,0.4,0.5]
positive_quantiles = [0.5,0.6,0.7,0.8]
quantiles = list(itertools.product(*[native_quantiles,positive_quantiles]))
MAs = [240, 480, 850]


"""
全量版：
    quantiles = 10x10 = 100
    mas = 5
    按照2013~2023，,1、2、3、4、5年
    合计：5x100 = 500
    4只基金一次回测： 73 s
    合计：5x100x73 = 36500 s
    16核一起跑：36500/3600 = 10 hours
    注：唉，这个需要的时间太多了，算了，不跑了，跑下面的精简版吧。
精简版：
    quantiles = 4x4 = 16
    mas = 3
    合计：3x16 = 48
    按照2013~2023，,1、2、3年，4只基金一次回测： 35 s
    合计：48x35 = 1680 s
    16核一起跑：1680/60 = 28 minutes
"""

def main(code, start_date, end_date, years, roll_months, cores):
    dfs = []
    pbar = tqdm(total=len(quantiles)*len(MAs))

    i = 1
    for q in quantiles:
        start = time.time()
        for ma in MAs:
            df_result = run(code, start_date, end_date, ma, q, years, roll_months, cores)
            df_result['负收益分位数'] = q[0]
            df_result['正收益分位数'] = q[1]
            df_result['移动均值'] = ma
            dfs.append(df_result)
            pbar.update(i)
            i+= 1
        logger.debug("完成组合 %r + %d 耗时：%s",q,ma,str(datetime.timedelta(seconds=time.time() - start)))
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
    parser.add_argument('-y', '--years', type=str, default='1,2,3,4,5', help="测试年份")
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
