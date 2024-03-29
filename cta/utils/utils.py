import datetime
import functools
import json
import logging
import math
import os
import time
import calendar

import dask
import numpy as np
import statsmodels.api as sm
import yaml
from backtrader_plotting.schemes import Tradimo
from dask import compute, delayed
from dateutil.relativedelta import relativedelta

logger = logging.getLogger(__name__)


class AttributeDict(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__


def load_config(path='./conf/config.yml'):
    if not os.path.exists(path):
        raise ValueError("配置文件[conf/config.yml]不存在!")
    f = open(path, 'r', encoding='utf-8')
    result = f.read()
    # 转换成字典读出来
    data = yaml.load(result, Loader=yaml.FullLoader)
    logger.info("读取配置文件:%s", path)
    return data


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


def serialize(obj, file_path):
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
        logger.debug("使用%d个并行，运行函数%s,参数：%r;%r", core_num, func.__name__, args, kwargs)
        func_partial = functools.partial(func, *args, **kwargs)

        # dask：https://juejin.cn/post/7083079485230153764
        # delayed是包装一下函数，compute是真正并行执行
        result = compute([delayed(func_partial)(i) for i in iterable])[0]

        client = Client(asynchronous=True, n_workers=4, threads_per_worker=2)

        return result


class AStockPlotScheme(Tradimo):
    """
    自定义的bar和volumn的显示颜色，follow A股风格
    """

    def _set_params(self):
        super()._set_params()
        self.barup = "#FC5D45"
        self.bardown = "#009900"
        self.barup_wick = self.barup
        self.bardown_wick = self.bardown
        self.barup_outline = self.barup
        self.bardown_outline = self.bardown
        self.volup = self.barup
        self.voldown = self.bardown


def calc_size(cash, price, commission_rate):
    """
    用来计算可以购买的股数：
    1、刨除手续费
    2、要是100的整数倍
    为了保守起见，用涨停价格来买，这样可能会少买一些。
    之前我用当天的close价格来算size，如果不打富余，第二天价格上涨一些，都会导致购买失败。
    """

    # 按照一个保守价格来买入
    size = math.ceil(cash * (1 - commission_rate) / price)

    # 要是100的整数倍
    size = (size // 100) * 100
    return size


def OLS(X, y):
    """
    做线性回归，返回 β0（截距）、β1（系数）和残差
    y = β0 + x1*β1 + epsilon
    参考：https://blog.csdn.net/chongminglun/article/details/104242342
    :param X: shape(N,M)，M位X的维度，一般M=1
    :param y: shape(N)
    :return:参数[β0、β1]，R2
    """
    assert not np.isnan(X).any(), f'X序列包含nan:{X}'
    assert not np.isnan(y).any(), f'y序列包含nan:{y}'

    # 增加一个截距项
    X = sm.add_constant(X)
    # 定义模型
    model = sm.OLS(y, X)  # 定义x，y
    results = model.fit()
    # 参数[β0、β1]，R2
    return results.params, results.rsquared


def load_params(name='params.yml'):
    if not os.path.exists(name):
        raise ValueError(f"参数文件[{name}]不存在，请检查路径")
    params = yaml.load(open(name, 'r', encoding='utf-8'), Loader=yaml.FullLoader)
    params = AttributeDict(params.items())
    return params


def get_monthly_duration(start_date, end_date):
    """
    把开始日期到结束日期，分割成每月的信息
    比如20210301~20220515 =>
    [   [20210301,20210331],
        [20210401,20210430],
        ...,
        [20220401,20220430],
        [20220501,20220515]
    ]
    """

    start_date = str2date(start_date)
    end_date = str2date(end_date)
    years = list(range(start_date.year, end_date.year + 1))
    scopes = []
    for year in years:
        if start_date.year == year:
            start_month = start_date.month
        else:
            start_month = 1

        if end_date.year == year:
            end_month = end_date.month + 1
        else:
            end_month = 12 + 1

        for month in range(start_month, end_month):

            if start_date.year == year and start_date.month == month:
                s_start_date = date2str(datetime.date(year=year, month=month, day=start_date.day))
            else:
                s_start_date = date2str(datetime.date(year=year, month=month, day=1))

            if end_date.year == year and end_date.month == month:
                s_end_date = date2str(datetime.date(year=year, month=month, day=end_date.day))
            else:
                _, last_day = calendar.monthrange(year, month)
                s_end_date = date2str(datetime.date(year=year, month=month, day=last_day))

            scopes.append([s_start_date, s_end_date])

    return scopes


def get_series(df, index_key, num):
    """
    # 先前key之前或者之后的series
    """
    try:
        loc = df.index.get_loc(index_key)
        s = df.iloc[loc + num]
        return s
    except KeyError:
        return None


# python -m utils.utils
if __name__ == '__main__':
    p = load_params('triples/params.yml')
    print(p)
    print(p.start_date)

    p = get_monthly_duration('20140101', '20230201')
    print(p)
