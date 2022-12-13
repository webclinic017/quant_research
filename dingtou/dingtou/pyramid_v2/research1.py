import argparse

import numpy as np
from pandas import DataFrame
from tabulate import tabulate

from dingtou.backtest import utils
from dingtou.pyramid.pyramid import main

class AttributeDict(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__

# python -m dingtou.pyramid.test_compose
if __name__ == '__main__':
    utils.init_logger()
    args = AttributeDict()
    args.start_date = '20140101'
    args.end_date = '20230101'
    args.amount = 2000000
    args.baseline = 'sh000001'
    args.grid_height = 0.01
    args.average_period = 480
    args.code = "510500"
    args.overlap_grid = 3

    df = DataFrame()
    for fund_code in funds:
        args.code = fund_code
        df1 = main(args,plot_file_subfix='one')
        df = df.append(df1,ignore_index=True)

    df.to_csv("debug/stat_one.csv")


    df = main(args,stat_file_name = "debug/stat_roll.csv",plot_file_subfix='roll')
    df = df[["基金代码", "投资起始", "投资结束", "期初资金", "期末现金", "期末持仓", "期末总值", "组合收益率",
                  "组合年化", "资金利用率", "基准收益", "基金收益", "买次", "卖次"]]
    df = df[["基金代码", "组合收益率","组合年化","期末现金", "期末持仓","基准收益", "基金收益", "买次", "卖次"]]
    print(tabulate(df, headers='keys', tablefmt='psql'))

    """
    测试和优化方案：
    1、每次投入总额、
    
    测试周期：  2013.3~2022.12（10年）
    测试窗口    2年、3年、4年、5年
    滚动窗口    3个月，每年4个月
    测试数量：  8x4+7x4+6x4+5x4= 32+28+24+20 = 104个测试（ 剩余年数 * 年移动4次）

    待优化参数：
    - 每次买入份数：
    
       
    """