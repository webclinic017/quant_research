这个是一个完整的backtrader的交易演示，

核心是策略类：KetlerStrategy，

用cerebro（脑波）加载这个策略，然后每天运行，
每天都看是否触发策略，如果触发，或买入、或卖出。

一些特殊说明：
- 为了适配A股的整手概念，写了一个自定义的sizer：AMarketSizer
- 买入的时候，只要市价单买入即可