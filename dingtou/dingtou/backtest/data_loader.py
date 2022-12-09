import logging
import pandas as pd
import os
import akshare as ak
import talib

logger = logging.getLogger(__name__)

def load(name, func, **kwargs):
    logger.info(f"加载{name}数据，函数:{func.__name__}，参数:{kwargs}")
    if not os.path.exists("./data"): os.mkdir("./data")

    values = [v for k,v in kwargs.items()]
    values = "_".join(values)
    file_name = f"data/{name}_{values}.csv"

    if not os.path.exists(file_name):
        df = func(**kwargs)
        logger.debug(f"调用了函数:{func.__name__}")
        df.to_csv(file_name)
    else:
        logger.debug(f"加载缓存文件:{file_name}")
        df = pd.read_csv(file_name)
    return df


def load_index(index_code):
    df_stock_index = load(index_code, ak.stock_zh_index_daily, symbol=index_code)
    df_stock_index['date'] = pd.to_datetime(df_stock_index['date'], format='%Y-%m-%d')
    df_stock_index['code'] = index_code  # 都追加一个code字段
    df_stock_index = df_stock_index.set_index('date')

    return df_stock_index

def load_funds(fund_codes,ma_days):
    data = {}
    for fund_code in fund_codes:
        df_fund = load_fund(fund_code)
        df_fund['ma'] = talib.SMA(df_fund.close, timeperiod=ma_days)
        df_fund['ma_net_value'] = talib.SMA(df_fund.net_value, timeperiod=ma_days)
        data[fund_code] = df_fund
    return data

def load_fund(fund_code):
    df_fund1 = load(fund_code, ak.fund_open_fund_info_em, fund=fund_code, indicator="累计净值走势")
    df_fund2 = load(fund_code, ak.fund_open_fund_info_em, fund=fund_code, indicator="单位净值走势")
    df_fund1['净值日期'] = pd.to_datetime(df_fund1['净值日期'], format='%Y-%m-%d')
    df_fund2['净值日期'] = pd.to_datetime(df_fund2['净值日期'], format='%Y-%m-%d')
    df_fund = df_fund1.merge(df_fund2,on='净值日期',how='inner')

    # TODO: 由于拆分、分红等，导致回测严重失真，决定将单位净值，也改成累计净值
    df_fund['单位净值'] = df_fund['累计净值']

    df_fund.rename(columns={'净值日期': 'date', '累计净值': 'close', '单位净值': 'net_value'}, inplace=True)
    df_fund = df_fund.set_index('date')
    df_fund['code'] = fund_code  # 都追加一个code字段
    return df_fund


def load_calendar(start_date, end_date):
    df = load("date", ak.tool_date_hist_sina)
    #    df = df[(df.date > start_date) & (df.date < end_date)]
    print("加载交易日期：%r~%r" % (df.iloc[0], df.iloc[-1]))
    return df