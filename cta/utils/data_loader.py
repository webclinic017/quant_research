import logging
import os
import backtrader as bt
import akshare as ak
import pandas as pd
import talib
from backtrader.feeds import PandasData
import tushare as ts

from utils import utils
from utils.utils import get_monthly_duration

logger = logging.getLogger(__name__)


def load(name, func, **kwargs):
    """
    通用加载函数：如果有csv文件就加载它，没有的话就去调用akshare函数，获得数据后保存到data目录
    :param name: 数据的名称，是个字符串标识而已
    :param func: 真正需要调用的akshare的函数
    :param kwargs: akshare函数所需要的动态参数
    :return:
    """

    logger.info(f"加载{name}数据，函数:{func.__name__}，参数:{kwargs}")
    if not os.path.exists("./data"): os.mkdir("./data")

    values = [str(v) for k, v in kwargs.items()]
    values = "_".join(values)
    file_name = f"data/{name}_{values}.csv"

    if not os.path.exists(file_name):
        df = func(**kwargs)
        logger.debug(f"调用了函数:{func.__name__}")
        df.to_csv(file_name)
    else:
        logger.debug(f"加载缓存文件:{file_name}")
        df = pd.read_csv(file_name,dtype={'code':str}) # code列要转成str，没有这个列系统会自动忽略
    return df


def load_index(index_code):
    df_stock_index = load(index_code, ak.stock_zh_index_daily, symbol=index_code)
    df_stock_index['date'] = pd.to_datetime(df_stock_index['date'], format='%Y-%m-%d')
    df_stock_index['code'] = index_code  # 都追加一个code字段
    df_stock_index = df_stock_index.set_index('date')

    return df_stock_index


def load_funds(codes):
    data = {}
    for code in codes:
        df_fund = load_fund(code)
        data[code] = df_fund
    return data


def load_stocks(codes, ma_days):
    data = {}
    for code in codes:
        df = load_stock(code)
        df['ma'] = talib.SMA(df.close, timeperiod=ma_days)
        data[code] = df
    return data


def load_stock(code):
    """加载股票数据"""
    # 调通用加载函数，加载数据
    df = load(name=code,
              func=ak.stock_zh_a_hist,
              symbol=code,
              period="daily",
              adjust="qfq")
    # 修改列名（为了兼容backtrader的要求的列名），以及转日期列为日期格式，并，设置日期列为索引列
    df['日期'] = pd.to_datetime(df['日期'], format='%Y-%m-%d')
    df.rename(columns={'日期': 'date',
                       '开盘': 'open',
                       '收盘': 'close',
                       '最高': 'high',
                       '最低': 'low',
                       '成交额': 'volume',
                       '涨跌幅': 'pcg_chg'}, inplace=True)
    df = df.set_index('date')
    df['code'] = code  # 都追加一个code字段
    return df


def load_fund(code):
    df_fund1 = load(code, ak.fund_open_fund_info_em, fund=code, indicator="累计净值走势")
    df_fund2 = load(code, ak.fund_open_fund_info_em, fund=code, indicator="单位净值走势")
    df_fund1['净值日期'] = pd.to_datetime(df_fund1['净值日期'], format='%Y-%m-%d')
    df_fund2['净值日期'] = pd.to_datetime(df_fund2['净值日期'], format='%Y-%m-%d')
    df_fund = df_fund1.merge(df_fund2, on='净值日期', how='inner')

    # TODO: 由于拆分、分红等，导致回测严重失真，决定将单位净值，也改成累计净值
    df_fund['单位净值'] = df_fund['累计净值']

    df_fund.rename(columns={'净值日期': 'date', '累计净值': 'close', '单位净值': 'net_value'}, inplace=True)
    df_fund = df_fund.set_index('date')
    df_fund['code'] = code  # 都追加一个code字段
    return df_fund


def load_hk_bought_stocks():
    """
    从2018.1.1至今的北上资金购买的每日沪深300数据
    这个是数据是我从聚宽爬下来的:
        ,date,name,code,share_ratio
        0,2018-01-02,平安银行,000001.XSHE,2.12
    :return:
    """
    file_name = "./data/hk_bought_stocks_20180101_now.csv"
    logger.debug(f"加载数据文件文件:{file_name}")
    df = pd.read_csv(file_name, dtype={'code': str})  # code列要转成str，没有这个列系统会自动忽略
    df['date'] = pd.to_datetime(df.date.apply(str), format='%Y-%m-%d')
    df['code'] = df.code.str[:6] #
    df = df.set_index('date')
    df = df.sort_index()
    return df


def load_hsgt_top10():
    df = load('hsgt_top10', __load_hsgt_top10)
    df['date'] = pd.to_datetime(df.date.apply(str), format='%Y-%m-%d')
    df = df.set_index('date')
    df = df.sort_index()
    return df


def __load_hsgt_top10():
    """
    https://tushare.pro/document/2?doc_id=48
    这个实现比较麻烦，主要是每次只能tushare返回300条,
    所以，我只能每个月下载一次，
    :param pro:
    :return:
    """
    pro = ts.pro_api(utils.load_config()['token'])
    dfs = []
    # 看了数据，是从2014.11才开始有的

    period_scopes = get_monthly_duration('20141101','20230201')
    from tqdm import tqdm

    bar = tqdm()
    for i,period_scope in enumerate(period_scopes):
        start = period_scope[0]
        end = period_scope[1]
        df = pro.hsgt_top10(start_date=start, end_date=end, market_type='1')
        dfs.append(df)
        df = pro.hsgt_top10(start_date=start, end_date=end, market_type='3')
        dfs.append(df)
        bar.update(i)
    bar.close()
    df = pd.concat(dfs)
    df['code'] = df.code.str[:6] # 遵从简化原则，不保留市场代码：600601.SH => 600601
    df.rename(columns={'trade_date': 'date', 'trade_code': 'code'}, inplace=True)
    return df



def load_moneyflow_hsgt():
    df = load('moneyflow_hsgt', __load_moneyflow_hsgt)
    df = set_date_index(df)
    df = df.sort_index()
    return df


def set_date_index(df,date_column='date'):
    df[date_column] = pd.to_datetime(df.date.apply(str), format='%Y-%m-%d')
    df = df.set_index(date_column)
    return df


def __load_moneyflow_hsgt():
    """
    https://tushare.pro/document/2?doc_id=47
    :param pro:
    :return:
    """
    pro = ts.pro_api(utils.load_config()['token'])

    # 看了数据，是从2014.11才开始有的
    dfs = []
    for year in range(2014, 2023):
        start = f'{year}0101'
        end = f'{year}1231'
        df = pro.moneyflow_hsgt(start_date=start, end_date=end)
        dfs.append(df)
    df = pd.concat(dfs)
    df.rename(columns={'trade_date': 'date'}, inplace=True)

    return df


def bt_wrapper(df, start_date, end_date):
    data = PandasData(dataname=df,
                      fromdate=start_date,
                      todate=end_date,
                      timeframe=bt.TimeFrame.Days,
                      plot=True)  # plot=False 不在plot图中显示个股价格

    return data
