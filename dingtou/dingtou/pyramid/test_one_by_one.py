import argparse

from pandas import DataFrame
from tabulate import tabulate

from dingtou.backtest import utils
from dingtou.pyramid.pyramid import main

class AttributeDict(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__

# python -m dingtou.pyramid.test_one_by_one
if __name__ == '__main__':
    utils.init_logger()
    args = AttributeDict()
    args.start_date = '20190101'
    args.end_date = '20220101'
    args.amount = 200000
    args.baseline = 'sh000001'
    args.grid_amount = 2000
    args.ma = 242
    funds = ["510310","510560","512000","512010","512040","512070","512330","512480","512560","512600"]
    df = DataFrame()
    for fund_code in funds:
        args.code = fund_code
        df1 = main(args,plot_file_subfix='one')
        df = df.append(df1,ignore_index=True)

    df.to_csv("debug/stat_one.csv")

    # df = df[["基金代码", "投资起始", "投资结束", "期初资金", "期末现金", "期末持仓", "期末总值", "组合收益率",
    #               "组合年化", "资金利用率", "基准收益", "基金收益", "买次", "卖次"]]
    df = df[["基金代码", "组合收益率","组合年化","基准收益", "基金收益", "买次", "卖次"]]
    print(tabulate(df, headers='keys', tablefmt='psql'))
