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

# python -m dingtou.pyramid.optimize
if __name__ == '__main__':
    utils.init_logger()
    args = AttributeDict()
    args.start_date = '20180217'
    args.end_date = '20210101'
    args.amount = 200000
    args.baseline = 'sh000001'
    # args.grid_amount = 3000
    args.grid_num = 10
    args.ma = 242
    args.type = 'fund'
    args.code = "510310,510560,512000,512010,512040,512070,512330,512480,512560,512600"

    df_result = DataFrame()
    for i in np.linspace(1000,10000,10):
        args.grid_amount = i
        df = main(args, stat_file_name="debug/stat_compose.csv", plot_file_subfix='compose')
        s = df.iloc[0]
        s['amount'] = i
        df_result = df_result.append(s,ignore_index=True)

    df_result.to_csv("debug/optimize.csv")
    df_result = df_result[["基金代码", "投资起始", "投资结束", "期初资金", "期末现金", "期末持仓", "期末总值", "组合收益率",
                  "组合年化", "资金利用率", "基准收益", "基金收益", "买次", "卖次"]]
    print(tabulate(df_result, headers='keys', tablefmt='psql'))


