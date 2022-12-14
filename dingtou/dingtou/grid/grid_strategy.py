import talib

from dingtou.utils import utils
from dingtou.backtest.strategy import Strategy
from dingtou.utils.utils import get_value, date2str
import logging

logger = logging.getLogger(__name__)


class GridStrategy(Strategy):
    """
    网格策略：https://ke.qq.com/course/335450/2701031918345818
    N：初始仓位
    H：网格高度，这里取ATR
    U：账户总额
    R：仓位风险（百份数，如10%）
    初始仓位 : N = (U * R) / (9 * ATR)
        推导：
        1、账户总风险：U*R
        2、初始网格总风险：N*6H，N是仓位，6H是6个格子的价格，也就是最开始买入的N跌倒6格止损线的时候的损失
        3、网格总风险：0.2N*5H + 0.2N*4H + 0.2N*3H + 0.2N*2H + 0.2N*H + N*6H = 9NH
            解释：5个网格子，每个格子高度是1个ATR，下跌到第6个格子，止损，
                所以要计算各次加仓后，不同筹码的风险，累加起来恰好是3NH，
                再加上初始的仓位N，就是他说的总风险是9NH，也就是损失的最多的钱是这么多。
        然后，总风险是9NH，总钱数是U，你最多风控是R，所以得到公式
        N = ( U * R ) / ( 9 * ATR )
    每次买、卖0.2N（5个格子，就是0.2）

    第二天，重新设置基准，使用第二天的ATR，

    为了防止踏空，持有一半仓位，然后另一半做网格交易，
    持仓上限 = 持仓下限+网格交易策略仓位的2倍
    持仓下限 = 买入持有的策略仓位

    加减仓，用的是ATR，1个ATR就是0.2个格子，就是原有仓位的0.2N，
    就决定了买多少股，买入价格就是当前价格，
    这个时候，重新计算买入成本，（之前成本*原有份数 + 新买入金额 ）/ 当前资金,
    这样，总是保存当前的成本，
    """

    def __init__(self, broker, initial_cash_amount):
        super().__init__(broker, None)
        self.U = initial_cash_amount
        self.position_lower = 0.5  # 最低持仓，为总值（基金市值+现金）的1/3，这个是为了收获上升通道的收益
        self.R = 1  # 10%的止损

    def set_data(self, df_baseline, funds_dict: dict):
        super().set_data(df_baseline, funds_dict)

        self.fund_weekly_dict = {}

        # 把日数据变成周数据，并，生成周频的ATR
        for code, df_daily_fund in funds_dict.items():
            df_daily_fund = df_daily_fund.rename(columns={'净值日期': 'date', '累计净值': 'close'})
            df_daily_fund['high'] = df_daily_fund.close
            df_daily_fund['low'] = df_daily_fund.close
            df_daily_fund['open'] = df_daily_fund.close
            df_weekly_fund = utils.day2week(df_daily_fund)
            df_weekly_fund['atr'] = talib.ATR(df_weekly_fund.high,
                                              df_weekly_fund.low,
                                              df_weekly_fund.close,
                                              timeperiod=20)
            df_weekly_fund['pct_chg'] = df_weekly_fund.close - df_weekly_fund.close.shift(1)
            self.fund_weekly_dict[code] = df_weekly_fund

    def risk_control(self, code, today, next_date, current_price):
        """
        看是否到了整体止损线，如果是，就清仓
        :param code:
        :param date:
        :param current_price:
        :return:
        """
        if self.broker.positions.get(code, None) is None: return False
        cost = self.broker.positions[code].cost

        _return = current_price / cost - 1
        # 计算目前是不是要止损了
        if _return < - self.R:  # self.R为10%，所以当低于-10%的时候，需要清仓
            logger.info("[%s]损失[%.2f%%]已大于阈值[%.2f%%]，清仓",
                        date2str(today),
                        _return * 100,
                        -self.R * 100)
            logger.info("[%s]成本[%.2f],当前价格[%.2f],损失[%.2f],总持仓[%.2f],现金[%.2f]",
                        date2str(today),
                        cost, current_price,
                        (cost - current_price) * self.broker.positions[code].position,
                        self.broker.get_total_position_value(),
                        self.broker.total_cash)
            self.broker.sell_out(code, next_date)
            return True

        return False

    def next(self, today, trade_date):
        super().next(today, trade_date)

        df_daily_fund = list(self.funds_dict.values())[0]  # TODO: 这里先选择了第一只基金，将来多只的时候，要遍历的
        df_weekly_fund = list(self.fund_weekly_dict.values())[0]  # TODO: 这里先选择了第一只基金，将来多只的时候，要遍历的

        # 先看日数据：1、止损 2、
        s_daily_fund = get_value(df_daily_fund, today)
        if s_daily_fund is None: return
        if self.broker.positions.get(s_daily_fund.code, None) is None:
            # 如果发现已经清仓了，重置总资金
            self.U = self.broker.total_cash
        # 做风控，每天都做一次封控
        if self.risk_control(code=s_daily_fund.code, today=today, next_date=today, current_price=s_daily_fund.close):
            # 触发风控，就请清仓走人
            return

        # 再看周数据
        s_weekly_fund = get_value(df_weekly_fund, today)
        if s_weekly_fund is None: return  # 如果不是周最后一天，返回
        if s_weekly_fund.atr is None: return  # 没有ATR也返回
        if df_weekly_fund.index.get_loc(today) < 0: return  # 防止越界

        # 获得上一周的信息
        s_last_weekly_fund = df_weekly_fund.iloc[df_weekly_fund.index.get_loc(today) - 1]
        last_week_date = s_last_weekly_fund._name

        # 本周信息
        weekly_price = close = s_weekly_fund.close
        atr = s_weekly_fund.atr
        import numpy as np
        if np.isnan(atr): return  # 如果ATR不存在，返回

        grid_height = atr / 5
        last_close = s_last_weekly_fund.close

        # 计算本周 - 上周的收盘价
        diff = close - last_close

        # 看价格差是ATR的几倍，这个也就是看是网格的几个格（1格是1个ATR）
        grid_num = diff // grid_height
        # print("====>",close, last_close, diff,grid_height,grid_num)
        if grid_num == 0:
            logger.debug("[%s]价[%.3f]和[%s]价[%.3f]差[%.3f],<1网格高度[%.3f]",
                         date2str(today),
                         close,
                         date2str(last_week_date),
                         last_close,
                         diff,
                         grid_height)
            return

        # 重新计算N，我理解，每一个时间T，ATR都会变，所以对应的风控的仓位都应该变化
        # print("====>",self.U,self.R,grid_num)
        N = (self.U * self.R) / (9 * grid_num)  # todo ？？？？9倍不对
        logger.debug("[%s]基金[%s]根据风控，确定最大买入风控仓位为[%d]份",
                     date2str(today),
                     s_weekly_fund.code,
                     N)

        # 是上涨，应该减仓
        if grid_num > 0:
            # 不一定要减仓，因为先看是否到了总值的1/3，如果不到不减仓
            # 这样是为了挣趋势上涨的钱，上涨应该卖，但是，为了踏空，保持一个1/3的仓位
            if self.broker.get_total_position_value() / self.broker.get_total_value() < self.position_lower:
                logger.debug("[%s]上涨,持仓值[%.2f/%.2f元]比例[%1.f%%]<阈值[%.1f%%]，不减仓",
                             date2str(today),
                             self.broker.get_total_position_value(),
                             self.broker.get_total_value(),
                             self.broker.get_total_position_value() * 100 / self.broker.get_total_value(),
                             self.position_lower * 100)
                return
            else:
                # 计算卖出份数，0.2N(仓位)*网格数
                position = int(grid_num * 0.2 * N)
                self.broker.sell(s_weekly_fund.code, trade_date, position=position)
                logger.debug("[%s]上涨,%d个网格,卖出基金[%s]%d份",
                             date2str(today),
                             grid_num,
                             s_weekly_fund.code,
                             position)

        # 是下跌，应该加仓
        else:
            # 计算出购入份数，0.2N(仓位)*网格数
            position = int(abs(grid_num * 0.2 * N))

            logger.debug("[%s]下跌,%d个网格,买入基金[%s]%d份",
                         date2str(today),
                         grid_num,
                         s_weekly_fund.code,
                         position)

            # 扣除手续费后，下取整算购买份数
            self.broker.buy(s_weekly_fund.code, trade_date, position=position)
