import datetime
import json
import pickle

import numpy as np
import logging
import os
import time
import functools

import dask
import yaml
from dask import compute, delayed
from dateutil.relativedelta import relativedelta

logger = logging.getLogger(__name__)

class AttributeDict(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__


def get_value(df, key):
    try:
        return df.loc[key]
    except KeyError:
        return None


def date2str(date, format="%Y%m%d"):
    return datetime.datetime.strftime(date, format)


def str2date(s_date, format="%Y%m%d"):
    return datetime.datetime.strptime(s_date, format)


def split_periods(start_date, end_date, window_years, roll_stride_months):
    """
        用来生成一个日期滚动数组，每个元素是开始日期和结束日期，每隔一个周期向前滚动

        比如:split('20120605','20151215',window_years=2,roll_stride_months=3)
        2012-06-15 00:00:00 2014-06-15 00:00:00
        2012-09-15 00:00:00 2014-09-15 00:00:00
        2012-12-15 00:00:00 2014-12-15 00:00:00
        2013-03-15 00:00:00 2015-03-15 00:00:00
        2013-06-15 00:00:00 2015-06-15 00:00:00
        2013-09-15 00:00:00 2015-09-15 00:00:00
        2013-12-15 00:00:00 2015-12-15 00:00:00

        :param start_date:
        :param end_date:
        :param window_years:
        :param roll_stride_months:
        :return:
        """

    all_ranges = []

    # 第一个范围
    start_roll_date = start_date
    end_roll_date = start_date + relativedelta(years=window_years)
    if end_roll_date > end_date:
        end_roll_date = end_date

    all_ranges.append([date2str(start_roll_date),
                       date2str(end_roll_date)])

    # while滚动期间的结束日期end_roll_date，小于总的结束日期end_date
    # 滚动获取范围
    start_roll_date = start_roll_date + relativedelta(months=roll_stride_months)
    while end_roll_date < end_date:
        # 滚动
        end_roll_date = start_roll_date + relativedelta(years=window_years)

        if end_roll_date > end_date:
            end_roll_date = end_date

        all_ranges.append([date2str(start_roll_date),
                           date2str(end_roll_date)])

        start_roll_date = start_roll_date + relativedelta(months=roll_stride_months)

    return all_ranges


def fit(data_x, data_y):
    """
    https://blog.csdn.net/zzu_Flyer/article/details/107634620
    :param data_x:
    :param data_y:
    :return:
    """

    # print(data_x,data_y)

    m = len(data_y)
    x_bar = np.mean(data_x)
    sum_yx = 0
    sum_x2 = 0
    sum_delta = 0
    for i in range(m):
        x = data_x[i]
        y = data_y[i]
        sum_yx += y * (x - x_bar)
        sum_x2 += x ** 2
    # 根据公式计算w
    w = sum_yx / (sum_x2 - m * (x_bar ** 2))

    for i in range(m):
        x = data_x[i]
        y = data_y[i]
        sum_delta += (y - w * x)
    b = sum_delta / m
    return w, b


def init_logger(file=False, simple=False, log_level=logging.DEBUG):
    print("开始初始化日志：file=%r, simple=%r" % (file, simple))

    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger('matplotlib.font_manager').disabled = True
    logging.getLogger('matplotlib.colorbar').disabled = True
    logging.getLogger('matplotlib').disabled = True
    logging.getLogger('fontTools.ttLib.ttFont').disabled = True
    logging.getLogger('PIL').setLevel(logging.WARNING)

    if simple:
        formatter = logging.Formatter('%(message)s')
    else:
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d P%(process)d: %(message)s')

    root_logger = logging.getLogger()
    root_logger.setLevel(level=log_level)

    def is_any_handler(handlers, cls):
        for t in handlers:
            if type(t) == cls: return True
        return False


    # 加入控制台
    if not is_any_handler(root_logger.handlers, logging.StreamHandler):
        stream_handler = logging.StreamHandler()
        root_logger.addHandler(stream_handler)
        print("日志：创建控制台处理器")

    # 加入日志文件
    if file and not is_any_handler(root_logger.handlers, logging.FileHandler):
        if not os.path.exists("./logs"): os.makedirs("./logs")
        filename = "./logs/{}.log".format(time.strftime('%Y%m%d%H%M', time.localtime(time.time())))
        t_handler = logging.FileHandler(filename, encoding='utf-8')
        root_logger.addHandler(t_handler)
        print("日志：创建文件处理器", filename)

    handlers = root_logger.handlers
    for handler in handlers:
        handler.setLevel(level=log_level)
        handler.setFormatter(formatter)

def serialize(obj,file_path):
    # pickle是二进制的，不喜欢，改成json序列化了
    # f = open(file_path, 'wb')
    # pickle.dump(obj, f)
    # f.close()
    with open(file_path, "w") as f:
        json.dump(obj, f, indent=2)

def unserialize(file_path):
    # f = open(file_path, 'rb')
    # obj = pickle.load(f)
    # f.close()
    with open(file_path, 'r') as f:
        obj = json.load(f)
    return obj

def __calc_OHLC_in_group(df_in_group):
    """
    计算一个分组内的最大的、最小的、开盘、收盘 4个值
    """
    # 先复制最后一条（即周五或者月末日），为了得到所有的字段
    df_result = df_in_group.tail(1).copy()
    # index.min()是本周第一天
    if 'open' in df_in_group: df_result['open'] = df_in_group.loc[df_in_group.index.min()]['open']
    # index.max()是本周最后天
    if 'close' in df_in_group: df_result['close'] = df_in_group.loc[df_in_group.index.max()]['close']
    # .max()是这一周的high列的最大值
    if 'high' in df_in_group: df_result['high'] = df_in_group['high'].max()
    # .min()是这一周的low列的最小值
    if 'low' in df_in_group: df_result['low'] = df_in_group['low'].min()
    if 'volume' in df_in_group: df_result['volume'] = df_in_group['volume'].sum()
    return df_result


def day2week(df):
    """
    把日频数据，变成，周频数据

    使用分组groupby返回的结果中多出一列，所以要用dropLevel 来drop掉
                                           code      open      high       low  ...   change   pct_chg      volume       amount
    datetime              datetime                                             ...
    2007-12-31/2008-01-06 2008-01-04  000636.SZ  201.0078  224.9373  201.0078  ...  -1.4360       NaN   352571.00   479689.500
    2008-01-07/2008-01-13 2008-01-11  000636.SZ  217.7585  223.1825  201.0078  ...  -6.5400 -0.027086   803621.33  1067058.340
    """
    # to_period是转成
    df_result = df.groupby(df.index.to_period('W')).apply(__calc_OHLC_in_group)
    if len(df_result.index.names) > 1:
        df_result = df_result.droplevel(level=0)  # 多出一列datetime，所以要drop掉
    df_result['pct_chg'] = df_result.close.pct_change()
    return df_result


def parallel_run(core_num, iterable, func, *args, **kwargs):
    """
    使用dask这个并行框架，来加速我们的函数并行运行
    :param CORE_NUM:
    :param iterable:
    :param func:
    :param args:
    :param kwargs:
    :return:

    dask文档：https://docs.dask.org/en/latest/scheduling.html
    """
    with dask.config.set(scheduler='processes', num_workers=core_num):
        """
        functools.partial就是帮助我们创建一个偏函数的，不需要我们自己定义int2()，可以直接使用下面的代码创建一个新的函数int2：
        >>> import functools
        >>> int2 = functools.partial(int, base=2)
        >>> int2('1000000')
        64
        # 偏函数partial：https://www.liaoxuefeng.com/wiki/1016959663602400/1017454145929440
        """
        logger.debug("使用%d个并行，运行函数%s,参数：%r;%r",core_num,func.__name__,args,kwargs)
        func_partial = functools.partial(func, *args, **kwargs)

        # dask：https://juejin.cn/post/7083079485230153764
        # delayed是包装一下函数，compute是真正并行执行
        result = compute([delayed(func_partial)(i) for i in iterable])[0]

        client = Client(asynchronous=True, n_workers=4, threads_per_worker=2)

        return result

def load_conf(conf_path):
    f = open(conf_path, 'r', encoding='utf-8')
    result = f.read()
    return yaml.load(result, Loader=yaml.FullLoader)
