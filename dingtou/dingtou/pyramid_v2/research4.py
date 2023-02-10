import argparse
import datetime
import logging
import time

from dateutil.relativedelta import relativedelta
from tqdm import tqdm

from dingtou.backtest import data_loader
from dingtou.pyramid_v2.research1 import run
from dingtou.utils import utils

logger = logging.getLogger(__name__)

"""
拉取所有的etf数据:
ETF数据大于1年过滤：387条 => 336条
ETF数据大于2年过滤：387条 => 196条
ETF数据大于3年过滤：387条 => 144条
ETF数据大于4年过滤：387条 => 87条
ETF数据大于5年过滤：387条 => 65条
ETF数据大于10年过滤：387条 => 23条
"""
import pandas as pd

LEAST_YEARS = 3


def load_all_etf_data(file="./research/etf_list.csv"):
    df = pd.read_csv(file, index_col=False)
    start_time = time.time()

    pbar = tqdm(total=len(df))

    data = {}
    for i, etf in df.iterrows():
        logger.debug("拉取ETF %s/%s的数据", str(etf['代码']), etf['名称'])
        df_etf = data_loader.load_fund(etf['代码'][:6])
        pbar.update(1)
        # time.sleep(0.1)
        data[f"{etf['代码'][:6]}:{etf['名称']}"] = df_etf
    pbar.close()
    # 耗时: 0:03:31.474244
    logger.debug("耗时: %s ", str(datetime.timedelta(seconds=time.time() - start_time)))
    return data




def filter_data(file='./research/etf_list.csv',years = LEAST_YEARS):
    """按照上市时间再过滤一次，用的是他的数据的日期，因为直接去上市日期信息有点费劲"""

    data = load_all_etf_data(file)
    left_data = {}
    for k, df in data.items():
        time_delta = relativedelta(datetime.datetime.now(), df.index[0])
        if (time_delta.years < years):
            logger.warning("%s , 上市时间%s小于%d年(%d年/%d月/%d天)",
                           k,
                           utils.date2str(df.index[0]),
                           LEAST_YEARS,
                           time_delta.years,
                           time_delta.months,
                           time_delta.days)
            continue
        left_data[k] = df

    logger.debug("ETF数据大于%d年过滤：%d条 => %d条",years, len(data), len(left_data))
    return left_data

def main(least,start_date, end_date, years, roll_months, cores):
    funds = filter_data(years=least)
    codes = []
    for f,_ in funds.items():
        code = f.split(":")[0]
        codes.append(code)
    logger.debug("一共买卖合计%d只ETF基金",len(codes))
    print(codes)
    df_result = run(",".join(codes), start_date, end_date, 850, [0.2,0.8], years, roll_months, cores)
    df_result['负收益分位数'] = 0.2
    df_result['正收益分位数'] = 0.8
    df_result['移动均值'] = 850
    df_result.to_csv(f"debug/etfilter_{start_date}_{end_date}_{years}_{roll_months}.csv")

# 本地测试
# python -m dingtou.pyramid_v2.research4 -s 20210101 -e 20230101 -y 2 -cs 4 -l 12

# 生产，上市3年以上的etf，142只，一起跑
# python -m dingtou.pyramid_v2.research4 -s 20130101 -e 20230101 -y 2 -cs 16 -l 3
if __name__ == '__main__':
    utils.init_logger(file=True)
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--start_date', type=str, default="20130101", help="开始日期")
    parser.add_argument('-e', '--end_date', type=str, default="20230101", help="结束日期")
    parser.add_argument('-cs', '--cores', type=int, default=5)
    parser.add_argument('-y', '--years', type=str, default='2,3,5', help="测试年份")
    parser.add_argument('-l', '--least', type=int, default=1, help="至少上市年份")
    parser.add_argument('-r', '--roll', type=int, default=3, help="滚动月份")
    args = parser.parse_args()

    start_time = time.time()
    main(
        args.least,
        args.start_date,
        args.end_date,
        args.years,
        args.roll,
        args.cores)

    logger.debug("耗时: %s ", str(datetime.timedelta(seconds=time.time() - start_time)))
