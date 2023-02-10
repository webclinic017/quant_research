# 说明

这个是一个完整的backtrader的交易演示，

核心是策略类：KetlerStrategy，

用cerebro（脑波）加载这个策略，然后每天运行，
每天都看是否触发策略，如果触发，或买入、或卖出。

一些特殊说明：
- 为了适配A股的整手概念，写了一个自定义的sizer：AMarketSizer
- 买入的时候，只要市价单买入即可

# 如何运行

1、安装python环境，推荐python3.8+，推荐使用virtualenv环境

2、运行 `pip install -r requirement.txt`，安装所需包，如果遗漏了那些包，请手工安装：`pip install xxxx`

3、退到cta目录，运行：

```commandline
python -m ketler.bt.main -s 20200101 -e 20220501 -c 300347.SZ
```
会产生回测的收益率，以及debug目录下的图表。