from collections import OrderedDict
import logging
from dateutil.relativedelta import relativedelta

from dingtou.backtest import metrics
from dingtou.utils.utils import date2str

logger = logging.getLogger(__name__)


def calculate_metrics(df_portfolio, df_baseline, df_fund, broker, initial_amount, start_date, end_date):
    def annually_profit(start_value, end_value, start_date, end_date):
        """
        细节：earn是一个百分比，不是收益/投入，而是终值/投入，这个是年化公式要求的，
        所以返回的时候，最终减去了1
        参考：https://www.pynote.net/archives/1667
        :param earn:
        :param broker:
        :return:
        """
        earn = end_value / start_value
        years = relativedelta(dt1=end_date, dt2=start_date).years
        months = relativedelta(dt1=end_date, dt2=start_date).months % 12
        years = years + months / 12
        return earn ** (1 / years) - 1

    # 计算各项指标
    stat = OrderedDict()
    stat["基金代码"] = df_fund.iloc[0].code
    stat["基准指数"] = df_baseline.iloc[0].code
    stat["投资起始"] = date2str(df_portfolio.index.min())
    stat["投资结束"] = date2str(df_portfolio.index.max())
    stat["定投起始"] = date2str(broker.df_trade_history.iloc[0].target_date)
    stat["定投结束"] = date2str(broker.df_trade_history.iloc[-1].target_date)

    start_value = initial_amount
    end_value = broker.get_total_value() - broker.total_commission
    stat["期初资金"] = start_value
    stat["期末现金"] = broker.total_cash
    stat["期末持仓"] = broker.get_total_position_value()
    stat["期末总值"] = broker.get_total_value()
    stat["组合盈利"] = end_value - start_value
    stat["组合收益"] = end_value / start_value - 1
    stat["组合年化"] = annually_profit(start_value, end_value, start_date, end_date)

    start_value = df_baseline.iloc[0].close
    end_value = df_baseline.iloc[-1].close
    stat["基准收益"] = end_value / start_value - 1
    stat["基准年化"] = annually_profit(start_value, end_value, start_date, end_date)

    start_value = df_fund.iloc[0].close
    end_value = df_fund.iloc[-1].close
    stat["基金收益"] = end_value / start_value - 1
    stat["基金年化"] = annually_profit(start_value, end_value, start_date, end_date)

    """
    接下来考察，仅投资用的现金的收益率，不考虑闲置资金了
    """

    # 盈利 = 总卖出现金 + 持有市值 - 总投入现金 - 佣金

    stat["夏普比率"] = metrics.sharp_ratio(df_portfolio.total_value.pct_change())
    stat["索提诺比率"] = metrics.sortino_ratio(df_portfolio.total_value.pct_change())
    stat["卡玛比率"] = metrics.calmar_ratio(df_portfolio.total_value.pct_change())
    stat["最大回撤"] = metrics.max_drawback(df_portfolio.total_value.pct_change())

    code = df_fund.iloc[0].code

    stat["买次"] = len(broker.df_trade_history[
                           (broker.df_trade_history.code == code) &
                           (broker.df_trade_history.action == 'buy')])
    stat["卖次"] = len(broker.df_trade_history[
                           (broker.df_trade_history.code == code) &
                           (broker.df_trade_history.action == 'sell')])

    stat["成本"] = -1 if broker.positions.get(code, None) is None else broker.positions[code].cost
    stat["持仓"] = -1 if broker.positions.get(code, None) is None else broker.positions[code].position
    stat["现价"] = df_fund.iloc[0].close
    stat["佣金"] = broker.total_commission

    return stat
