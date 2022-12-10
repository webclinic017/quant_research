import logging

logger = logging.getLogger(__name__)


def calculate_grid_values_by_statistics(fund_dict, grid_amount, grid_num):
    """
    返回各个基金的格子高度，和，格子最基础的买入份数，
    计算方法：
        grid_amount(一个格子的钱数) / 历史移动均值的最后一天的值
    改进：
        做了一些改进，分开了上涨和下跌的，本来想用atr来着，但是没有每天的HLOC值。
    :param fund_dict:
    :param grid_amount: 一网格的钱数
    :param grid_num: 上涨/下跌的格子数，默认10
    :return:
    """
    down_grid_height_dict = {}
    up_grid_height_dict = {}
    grid_share_dict = {}
    for code, df_fund in fund_dict.items():
        # 乖离率
        df_fund['diff_percent'] = (df_fund.close - df_fund.ma) / df_fund.ma
        # 超过MA的80%的分位数
        positive = df_fund[df_fund.diff_percent > 0].diff_percent.quantile(0.8)
        # 低于MA的80%的分位数
        negative = df_fund[df_fund.diff_percent < 0].diff_percent.quantile(0.2)

        # 上下一共分为N个格子
        up_grid_height = positive / grid_num
        down_grid_height = -negative / grid_num
        logger.debug("网格高度为：上%.2f%%，下%.2f%%", up_grid_height * 100, down_grid_height * 100)
        up_grid_height_dict[code] = up_grid_height
        down_grid_height_dict[code] = down_grid_height

        # 用移动均值的最后一天来作为格子的买入份数计算
        grid_share_dict[code] = int(grid_amount / df_fund.iloc[-1].ma)

        logger.debug("找出基金[%s]和移动均线偏离80%%的收益率边界值为：[%.1f%%~%.1f%%]",
                     df_fund.iloc[0].code,
                     positive * 100,
                     negative * 100)

        logger.debug("按照基金[%s]最新的净值均值，设定的购买金额[%.1f]，可以买入网格基准份数[%.0f]份",
                     df_fund.iloc[0].code,
                     grid_amount,
                     grid_share_dict[code])

    return up_grid_height_dict,down_grid_height_dict, grid_share_dict
