import logging
import pandas as pd
import os
import akshare as ak

logger = logging.getLogger(__name__)

def load(name, func, **kwargs):
    logger.info(f"加载{name}数据，函数:{func.__name__}，参数:{kwargs}")
    if not os.path.exists("./data"): os.mkdir("./data")
    file_name = f"data/{name}.csv"
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


def load_fund(fund_code):
    df_fund = load(fund_code, ak.fund_open_fund_info_em, fund=fund_code, indicator="累计净值走势")
    if df_fund is None or '净值日期' not in df_fund.columns:
        logger.error("基金[%s]数据加载出现问题：%r", fund_code, df_fund)
        raise
    df_fund['净值日期'] = pd.to_datetime(df_fund['净值日期'], format='%Y-%m-%d')
    df_fund['code'] = fund_code  # 都追加一个code字段
    df_fund.rename(columns={'净值日期': 'date', '累计净值': 'close'}, inplace=True)
    df_fund = df_fund.set_index('date')

    return df_fund


def load_calendar(start_date, end_date):
    df = load("date", ak.tool_date_hist_sina)
    #    df = df[(df.date > start_date) & (df.date < end_date)]
    print("加载交易日期：%r~%r" % (df.iloc[0], df.iloc[-1]))
    return df