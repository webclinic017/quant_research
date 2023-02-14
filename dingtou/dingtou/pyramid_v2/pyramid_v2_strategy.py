import os.path

from dingtou.utils import utils
from dingtou.backtest.strategy import Strategy
from dingtou.utils.utils import get_value, date2str, unserialize, serialize
import logging
import talib
import pandas as pd

logger = logging.getLogger(__name__)


class PyramidV2Strategy(Strategy):
    """
    上一个PyramidStrategy效果还是一般，开始组合挺好的，但是后来发现了一个bug，只用到了第一个标的的数据，
    仔细再看了王纯迅的视频[年化20%的算法交易](https://www.bilibili.com/video/BV1d5411P7Lt)，
    发现了很多细节还是不太一样，需要改进：

    - 他就用的当天的价格作为成交价格，这个是合理的，
        因为可以比对着中证500指数，10分钟收盘前，按照当天价格下单，基金3点前1个价格，3点后按明日的收盘时候的价格来，
        基金每天之有1个价格，当天下单只有1/10000左右的偏差，而第二天下单偏差就大了去了，
        可以参考[盘中实时净值估算图](http://fund.eastmoney.com/007338.html)。

    - 增加了对敲，也就是不再是尖对尖的金字塔，而是错峰的2个金字塔，重叠部分，就是对敲部分
      这部分，我思考后，对敲部分是一个区域，可以分布在均线两边，也可以是分布在均线之下，我选择了在均线之下

    - 他说(3分58秒)，统计完偏离均线的幅度的分布后，他设计了一个跟随区间系统，来调整网格，这里讲的很不清楚，我心存疑惑：
        * 为何要做偏离均线幅度的统计？偏离比较大，知道是比80%的分位数还大，又如何？
        * "根据价格偏离年线的幅度，来增加他的网格的格子的幅度"？这最关键的一句话究竟是啥意思？
           是说，格子的区域增大，1个格子的高度不变，只是格子数增加了？
           还是说，是格子数不变，但是每个格子的高度变化？
           我觉得，格子区域增大，1个格子高度不变更靠谱，因为他后来提到1个格子千分之8（7份36秒）

    - 他提到一个跟随代码(5:38)，跟随系数(7:48)，这个跟随是啥意思？当然，肯定是和上年的格子幅度是联动的。

    - 他提到了择时策略，网格和金字塔都是为了不择时，为何他又提到增加一个择时策略呢？

    - 他还提到要算一个短期走势概率是为了什么？他说是为了分配闲钱到短线投资，是指调配好闲置资金去债市、货币基金么？

    摘录自评论：
    >再定期调整网格的百分比，然后再在一定价格上下边界停止网格进行统一全仓清仓的筹码归集，
    >就是因为我合作的券商是有超低手续费+自动网格交易系统的，
    >我写这个系统，为的就是我在券商那挂一个自动网格交易，然后定期比如三五天或者每周，
    >根据我的算法交易给出的误差，去券商那调整网格参数或者人工买入卖出做份额调整。
    >这样能兼顾密集自动交易和少量人工交易修正。


.grid_height,
                                 args.quantile_positive,
                                 args.quantile_negative,
                                 args.ma,
                                 args.end_date
    """

    def __init__(self,
                 broker,
                 args,
                 last_grid_position_file_path=None):
        super().__init__(broker, None)
        self.args = args
        self.grid_height = args.grid_height  # 上涨时候网格高度，百分比，如0.008
        self.quantile_positive = args.quantile_positive
        self.quantile_negative = args.quantile_negative
        self.grid_amount = args.grid_amount

        if last_grid_position_file_path and os.path.exists(last_grid_position_file_path):
            logger.debug("存在最后的网格位置文件，加载它：%s", last_grid_position_file_path)
            self.last_grid_position_dict = unserialize(last_grid_position_file_path)
        else:
            self.last_grid_position_dict = {}

        self.last_grid_position_file_path = last_grid_position_file_path # 序列化文件
        self.positive_threshold_dict = {}
        self.negative_threshold_dict = {}

        self.ma_days = args.ma

        if type(args.end_date) == str: end_date = utils.str2date(args.end_date)
        self.end_date = end_date


        # 统计用
        self.buy_ok = 0
        self.sell_ok = 0
        self.buy_fail = 0
        self.sell_fail = 0

    def set_data(self, df_baseline, funds_dict: dict):
        super().set_data(df_baseline, funds_dict)

        for code, df_daily_fund in funds_dict.items():
            # 留着这个代码恶心自己，这个用到了未来函数
            # df = df_daily_fund[df_daily_fund.index<=self.end_date]
            # avg_close = (df.iloc[-self.ma_days:].close.max() + df.iloc[-self.ma_days:].close.min())/2
            # 这才是正确做法，每天都算前3年的平均值
            logger.info("计算平均线，MA[%d]", self.ma_days)
            if self.ma_days <= 0:
                # 如果是self.ma_days是负值，回看前N天的最大最小值的中间值
                maxs = talib.MAX(df_daily_fund.close, timeperiod=-self.ma_days)
                mins = talib.MIN(df_daily_fund.close, timeperiod=-self.ma_days)
                df_daily_fund['ma'] = (maxs + mins) / 2
                # 额外画上一个年线参考
                df_daily_fund['ma242'] = talib.SMA(df_daily_fund.close, timeperiod=242)
                logger.info('按照最大最小值计算MA')
            else:
                # 如果是self.ma_days是正值，用N天的均线
                # df_daily_fund['ma'] = talib.SMA(df_daily_fund.close, timeperiod=self.ma_days)
                # 不用talib的sma，是因为，ma_days取850的时候，会出现850个na，所以用pandas的rolling，使用min_periods避免nan
                df_daily_fund['ma'] = df_daily_fund.close.rolling(window=self.ma_days,min_periods=1).mean()
                logger.info('按照移动平均计算MA')

            # 计算价格到均价的距离
            df_daily_fund['diff_percent_close2ma'] = (df_daily_fund.close - df_daily_fund.ma) / df_daily_fund.ma

            # 超过MA的80%的分位数
            positive_threshold = df_daily_fund[
                df_daily_fund.diff_percent_close2ma > 0].diff_percent_close2ma.quantile(self.quantile_positive)
            self.positive_threshold_dict[code] = 1 + positive_threshold // self.grid_height
            logger.info("[%s] %.0f%%分位数的正收益为%.2f%%, 在第%d个格",
                         code,
                         self.quantile_positive*100,
                         positive_threshold*100,
                         self.positive_threshold_dict[code] )

            # 低于MA的20%的分位数
            negative_threshold = df_daily_fund[
                df_daily_fund.diff_percent_close2ma < 0].diff_percent_close2ma.quantile(1 - self.quantile_negative)
            self.negative_threshold_dict[code] = negative_threshold // self.grid_height
            logger.info("[%s] %.0f%%分位数的负收益为%.2f%%, 在第%d个格",
                         code,
                         self.quantile_negative*100,
                         negative_threshold*100,
                         self.negative_threshold_dict[code] )

            # 这个是为了画图用，画出上下边界区域
            df_daily_fund['ma_upper'] = df_daily_fund.ma * (1 + positive_threshold)
            df_daily_fund['ma_lower'] = df_daily_fund.ma * (1 + negative_threshold)


    def next(self, today, trade_date):
        super().next(today, trade_date)

        # 遍历每一只基金，分别处理
        for fund_code, df_fund in self.funds_dict.items():
            diff2last,price,ma = self.get_current_diff_percent(df_fund,today)
            self.handle_one_fund(fund_code, today, price, ma, diff2last)


    def get_current_diff_percent(self,df_daily_fund,today):
        """
        获得当前价格，距离均线的距离，
        :param df_daily_fund:
        :param today:
        :return:
        """
        s_daily_fund = get_value(df_daily_fund, today)
        if s_daily_fund is None: return None,None,None
        if pd.isna(s_daily_fund.diff_percent_close2ma): return None,None,None
        return s_daily_fund.diff_percent_close2ma, s_daily_fund.close, s_daily_fund.ma

    def handle_one_fund(self, code, today, price, ma, diff2last):
        """
        处理一只基金
        :param df_daily_fund:
        :param today:
        :param target_date:
        :return: 相关的信息
        """
        if diff2last is None:
            return None

        # 当前和上次位置的距离（单位是百分比）
        # 得到格子数，有可能是负数，。。。， -3，-2，-1，1，2，3，。。。，下面的if/else写法就是为了得到这个当前点位位于的格子编号
        current_grid_position = diff2last // self.grid_height if diff2last < 0 else 1 + diff2last // self.grid_height
        last_grid_position = 0 if self.last_grid_position_dict.get(code,None) is None else self.last_grid_position_dict[code]

        if current_grid_position == last_grid_position:
            logger.debug("[%s] %s 当前格子没有变化： 第%d个格子",date2str(today),code,current_grid_position)
            return None # 在同一个格子，啥也不干


        """
        如果在均线下方，且，比上次的还低1~N个格子，那么就买入
        实盘的时候，我会把每个标的的最后一次的购买网格位置记录到文件中，
        但是如果没有记录，说明是第一次买入，我本来计划判断是在下跌趋势（就是目前价格是10个交易日内最低），
        但是后来觉得没有必要，因为只要是在这个点位就是我要购入的点位，不管他上涨还是下跌，直到他趋势反转再跌下来，我才会再买。
        """
        amount = self.grid_amount * abs(current_grid_position)

        if current_grid_position < 0 and \
                current_grid_position < last_grid_position and \
                current_grid_position < self.negative_threshold_dict[code]:
            # 根据偏离均线幅度，决定购买的份数
            # 买入
            if self.broker.buy(code,today,amount=amount * self.args.buy_factor):
                msg = "[%s] %s当前价格[%.4f]，距离均线[%.4f]，距离百分比[%.1f%%]，距离[%d]格,低于上次[第%d格],买入%.1f元  基<---钱" % (
                             date2str(today),
                             code,
                             price,
                             ma,
                             diff2last * 100,
                             current_grid_position,
                             last_grid_position,
                             amount)
                logger.info(msg)
                # logger.debug("current_grid_position > self.negative_threshold: %d > %d",
                #              current_grid_position, self.negative_threshold_dict[code])
                self.last_grid_position_dict[code] = current_grid_position
                if self.last_grid_position_file_path:
                    serialize(self.last_grid_position_dict,self.last_grid_position_file_path)
                return msg


        # logger.debug("current:%d,last:%d,diff:%.2f%%",current_grid_position,last_grid_position,diff2last*100)

        # 在均线之上，且，超过之前的高度(diff>0)，且，至少超过1个网格(grid_num>=1)，就卖
        if current_grid_position > last_grid_position and \
                current_grid_position > 0 and \
                current_grid_position > self.positive_threshold_dict[code]:

            # 扣除手续费后，下取整算购买份数
            if self.broker.sell(code, today, amount=amount * self.args.sell_factor):
                msg = "[%s] %s当前价格[%.4f],距离均线[%.4f],距离百分比[%.1f%%],距离[%d]格,高于上次[第%d格],卖出%.1f元  基===>钱" % (
                        date2str(today),
                        code,
                        price,
                        ma,
                        diff2last * 100,
                        current_grid_position,
                        last_grid_position,
                        amount)
                logger.info(msg)
                # logger.debug("current_grid_position > self.positive_threshold: %d > %d",
                #              current_grid_position, self.positive_threshold_dict[code])
                self.last_grid_position_dict[code] = current_grid_position
                if self.last_grid_position_file_path:
                    serialize(self.last_grid_position_dict,self.last_grid_position_file_path)
                return msg

        # logger.debug("[%s] 未触发交易: %s 差异[%.4f],当前格[%d],上次格[%d],正阈值格[%d],负阈值格[%d]",
        #              date2str(today),
        #              code,
        #              diff2last,
        #              current_grid_position,
        #              last_grid_position,
        #              self.positive_threshold_dict[code],
        #              self.negative_threshold_dict[code])
        return None