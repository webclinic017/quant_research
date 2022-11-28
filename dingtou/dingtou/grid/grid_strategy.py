import talib

from dingtou.backtest import utils
from dingtou.backtest.strategy import Strategy
from dingtou.backtest.utils import get_value, date2str
import logging

logger = logging.getLogger(__name__)


class GridStrategy(Strategy):
    """
    网格策略：https://ke.qq.com/course/335450/2701031918345818
    N：初始仓位
    H：网格高度，这里取ATR
    U：账户总额
    R：仓位风险（百分数，如10%）
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
    这个时候，重新计算买入成本，（之前成本*原有分数 + 新买入金额 ）/ 当前资金,
    这样，总是保存当前的成本，
    """

    def __init__(self, broker, initial_cash_amount, ):
        super().__init__(broker, cash_distribute)
        self.U = initial_cash_amount
        self.position_lower = 0.3  # 最低持仓，为总值（基金市值+现金）的1/3，这个是为了收获上升通道的收益
        self.R = 0.1  # 10%的止损

    def set_data(self, df_baseline, funds_dict: dict):
        super().set_data(df_baseline, funds_dict)

        # 把日数据变成周数据，并，生成周频的ATR
        for code, df_daily_fund in funds_dict.items():
            df_daily_fund = df_daily_fund.rename(columns={'净值日期': 'date', '累计净值': 'close'})
            df_daily_fund['high'] = df_daily_fund.close
            df_daily_fund['low'] = df_daily_fund.close
            df_daily_fund['open'] = df_daily_fund.close
            df_weekly_fund = utils.day2week(df_daily_fund)
            df_weekly_fund['atr'] = talib.ATR(df_weekly_fund.high, df_weekly_fund.low, df_weekly_fund.close,
                                              timeperiod=20)
            funds_dict[code] = df_weekly_fund

    def risk_control(self, code, next_date, current_price):
        """
        看是否到了整体止损线，如果是，就清仓
        :param code:
        :param date:
        :param current_price:
        :return:
        """

        cost = self.broker.positions[code].cost

        _return = current_price / cost - 1
        # 计算目前是不是要止损了
        if _return < - self.R:  # self.R为10%，所以当低于-10%的时候，需要清仓
            self.broker.sell_out(code, next_date)
            logger.info("损失[%.2f]已大于阈值[%.2f]，清仓", _return, -self.R)
            return True

        return False

    def next(self, today, next_trade_date):
        super().next(today, next_trade_date)

        df_baseline = self.df_baseline
        df_fund = list(self.funds_dict.values())[0]  # TODO: 这里先选择了第一只基金，将来多只的时候，要遍历的

        code = df_fund.iloc[0].code

        if self.broker.positions.get(code,None) is None:
            # 如果发现已经清仓了，重置总资金
            self.U = self.broker.cash

        # 做风控，每天都做一次封控
        if self.risk_control(code,next_trade_date):
            # 触发风控，就请清仓走人
            return

        # 如果不是周线
        s_fund = get_value(df_fund, today)
        if s_fund is None: return  # 如果不是周最后一天，返回
        if s_fund.atr is None: return  # 没有ATR也返回
        if df_fund.index.get_loc(today) < 0: return  # 防止越界
        code = None if s_fund is None else s_fund.code

        # 获得上一周的信息
        s_last_fund = df_baseline.iloc[df_fund.index.get_loc(today) - 1]
        last_date = s_last_fund.index

        close = s_fund.close
        atr = s_fund.atr
        last_close = s_last_fund.close

        # 计算本周 - 上周的收盘价
        diff = close - last_close

        # 看价格差是ATR的几倍，这个也就是看是网格的几个格（1格是1个ATR）
        atr_times = diff % atr
        if atr_times == 0:
            logger.debug("当前[%s]价格[%.1f]和上一个[%s]价格[%.1f]相差不到1个ATR[%.1f]",
                         date2str(today),
                         close,
                         date2str(last_date),
                         last_close,
                         atr)
        return

        # 重新计算N，我理解，每一个时间T，ATR都会变，所以对应的风控的仓位都应该变化
        N = ( self.U * self.R ) / ( 9 * atr )
        logger.debug("[%s]计算基金[%s]的",date2str(date),code)

        # 是上涨，应该减仓
        if atr_times > 0:
            # 不一定要减仓，因为先看是否到了总值的1/3，如果不到不减仓
            # 这样是为了挣趋势上涨的钱，上涨应该卖，但是，为了踏空，保持一个1/3的仓位
            if self.broker.get_total_position_value() / self.broker.get_total_value() < self.position_upper:
                logger.debug("持仓值[%.1f]比例[%1.f%%]小于资产值[%.1f]，不减仓，继续持有",
                             self.broker.get_total_position_value(),
                             self.broker.get_total_position_value() * 100 / self.broker.get_total_value(),
                             self.broker.get_total_value())
                return
            else:
                amount = atr_times * N
                self.broker.sell(code, next_trade_date, amount)
        # 是下跌，应该加仓
        else:
            # 计算出购入金额
            amount, ratio = self.cash_distribute.calculate(sma_value, current_value=index_close)

            df_baseline.loc[today, 'signal'] = index_close * ratio  # 买信号

            # 扣除手续费后，下取整算购买份数
            self.broker.buy(code, next_trade_date, amount)
