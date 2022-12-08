import logging

logger = logging.getLogger(__name__)




def main(args):
    fund_codes = args.code.split(",")
    logger.debug("测试%d只ETF基金",len(fund_codes))





"""

# 优化

- 考虑到只投到一个etf基金，会让资金利用率偏低，所以想到准备一揽子基金来做这个事。
- 每只基金来抢这个资金，谁有投资机会就让谁来投
- 每只基金都默认采用20、60、120、240，来作为均线
- 网格尽量设置成10，所以要对每个基金做偏离均线的统计，从而动态确定网格高度
- 网格按照80%的原则来统计分位数，如80%在18%，那么网格高度就是：18%/10 = 2%
- 每次购买某个基金不能按照份数来，会导致资金分配不均匀，按照金额来投
- 每次投入的金额是一个超参，需要来跑出一个最优的

python -m dingtou.pyramid.train
-c 510310,510560,512000,512010,512040,512070,512330,512480,512560,512600 \
--start_date 20180101
--end_date 20210101 \
--baseline sh000001 \
--amount 500000 \
--grid_amount = 1000 \
--grid_height = 0.02

"""
import argparse

from dingtou.backtest import utils

if __name__ == '__main__':
    utils.init_logger()

    # 获得参数
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--start_date', type=str, default="20150101", help="开始日期")
    parser.add_argument('-e', '--end_date', type=str, default="20221201", help="结束日期")
    parser.add_argument('-b', '--baseline', type=str, default=None, help="基准指数，这个策略里就是基金本身")
    parser.add_argument('-m', '--ma', type=int, default=4, help="基金移动均值天数")
    parser.add_argument('-c', '--code', type=str, help="股票代码")
    parser.add_argument('-a', '--amount', type=int, default=500000, help="投资金额，默认50万")
    parser.add_argument('-gm', '--grid_amount', type=int, default=1000, help="每网格买入钱数")
    parser.add_argument('-gh', '--grid_height', type=float, default=0.02, help="网格高度,默认2%")
    args = parser.parse_args()

    main(args)