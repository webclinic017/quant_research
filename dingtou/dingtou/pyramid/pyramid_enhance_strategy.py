from dingtou.backtest.strategy import Strategy
from dingtou.backtest.utils import get_value, date2str
import logging
import talib
import pandas as pd

logger = logging.getLogger(__name__)


class PyramidEnhanceStrategy(Strategy):
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

    """

    def __init__(self, broker, policy,grid_height, overlap_grid_num):
        super().__init__(broker, None)
        # self.grid_height = 0.008 # 千分之8的格子高度，是王纯迅在视频里透露的：https://www.bilibili.com/video/BV1d5411P7Lt
        self.grid_height = grid_height  # 上涨时候网格高度，百分比，如0.008
        self.overlap_grid_num = overlap_grid_num  # 对敲重叠区域格子数，比如 5 个
        self.policy = policy
        self.last_grid_position_dict = {}

    def set_data(self, df_baseline, funds_dict: dict):
        super().set_data(df_baseline, funds_dict)
        for code, df_daily_fund in funds_dict.items():
            df_daily_fund['diff_percent_close2ma'] = (df_daily_fund.close - df_daily_fund.ma) / df_daily_fund.ma
        for fund_code in funds_dict.keys():
            self.last_grid_position_dict[fund_code] = 0

    def next(self, today, trade_date):
        super().next(today, trade_date)

        # 遍历每一只基金，分别处理
        for fund_code, df_fund in self.funds_dict.items():
            self.handle_one_fund(df_fund, today, trade_date)

    def handle_one_fund(self, df_daily_fund, today, target_date):
        """
        处理一只基金
        :param df_daily_fund:
        :param today:
        :param target_date:
        :return:
        """

        # 先看日数据：1、止损 2、
        s_daily_fund = get_value(df_daily_fund, today)
        if s_daily_fund is None: return
        if pd.isna(s_daily_fund.diff_percent_close2ma): return

        # 当前和上次位置的距离（单位是百分比）
        diff2last = s_daily_fund.diff_percent_close2ma - self.last_grid_position_dict[s_daily_fund.code]
        # 得到格子数，有可能是负数，。。。， -3，-2，-1，1，2，3，。。。，下面的if/else写法就是为了得到这个当前点位位于的格子编号
        current_grid_position = diff2last // self.grid_height if diff2last < 0 else 1 + diff2last // self.grid_height
        last_grid_position = self.last_grid_position_dict[s_daily_fund.code]

        if current_grid_position == last_grid_position: return  # 在同一个格子，啥也不干

        # 如果在均线下方，且，比上次的还低1~N个格子，那么就买入
        if current_grid_position < 0 and current_grid_position < last_grid_position:
            # 根据偏离均线幅度，决定购买的份数
            positions = self.policy.calculate(current_grid_position,'buy')
            # 买入
            if self.broker.buy(s_daily_fund.code,
                               target_date,
                               position=positions):
                logger.debug("[%s]%s距离均线%.1f%%/%d个格,低于上次历史%.1f%%,买入%.1f份  基<---钱",
                             date2str(today),
                             s_daily_fund.code,
                             s_daily_fund.diff_percent_close2ma * 100,
                             current_grid_position,
                             self.last_grid_position_dict[s_daily_fund.code] * 100,
                             positions)
                self.last_grid_position_dict[s_daily_fund.code] = current_grid_position
            return

        # 如果在均线下方，且，比上次的还高1~N个格子，且，在对敲(overlap)区，那么就卖出对应的份数
        if 0 > current_grid_position > last_grid_position and \
                abs(current_grid_position) < self.overlap_grid_num:
            positions = self.policy.calculate(current_grid_position,'sell')
            if self.broker.sell(s_daily_fund.code, target_date, position=positions):
                logger.debug(">>[%s]%s均线下方%.1f%%/第%d格,高于上次(第%d格),对敲卖出%.1f份  (对敲) 基===>钱",
                             date2str(today),
                             s_daily_fund.code,
                             s_daily_fund.diff_percent_close2ma * 100,
                             current_grid_position,
                             self.last_grid_position_dict[s_daily_fund.code] * 100,
                             positions)
                self.last_grid_position_dict[s_daily_fund.code] = current_grid_position

        # 在均线之上，且，超过之前的高度(diff>0)，且，至少超过1个网格(grid_num>=1)，就卖
        if current_grid_position > last_grid_position > 0:

            positions = self.policy.calculate(current_grid_position,'sell')
            # 扣除手续费后，下取整算购买份数
            if self.broker.sell(s_daily_fund.code, target_date, position=positions):
                logger.debug(">>[%s]%s距离均线%.1f%%/%d个格,高于上次历史%.1f%%,卖出%.1f份  基===>钱",
                             date2str(today),
                             s_daily_fund.code,
                             s_daily_fund.diff_percent_close2ma * 100,
                             current_grid_position,
                             self.last_grid_position_dict[s_daily_fund.code] * 100,
                             positions)
                self.last_grid_position_dict[s_daily_fund.code] = current_grid_position * self.grid_height[s_daily_fund.code]
