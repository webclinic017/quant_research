# 回测内容
这个是参考王纯迅的[纯享投资](https://www.bilibili.com/video/BV1rz4y1k77Y)，
来做的一个回测项目。

重点参考了[【硬核】年化20%的算法交易，财务自由就靠他了](https://www.bilibili.com/video/BV1d5411P7Lt)。

# 算法

跟随系数？

- 根据历史，计算上下的区间，也就是覆盖80%的上和下就可以，形成一个网格区间，这个区间是变化，随着时间向前会不断地变化。
- 某天都可以计算出偏离均线的百分比，当发现这个百分比下降一格，就可以出发网格交易了。
- 回顾了510500中证500ETF的偏离年线的百分比，上80%在18%，下80%在-17%，所以，综合认为在上下18%就可以，
- 我们可以设计一个算法，每2%是一个格子，每下跌1格就加仓多1份，每上升1格就多减仓1份
- 只有跌破年线才买入，只有上串年线才卖出


# ETF基金

截至2022年10月10日，全市场ETF总共有**745**只，其中被动指数型基金有634只，QDII基金有45只，货币市场型基金27只。

- 宽基指数ETF数量152只，规模4562亿元，占股票类ETF总规模39%。
- 行业指数ETF数量334只，规模4374亿元，占股票类ETF总规模38%。
- 跨境型ETF数量72只，规模为1679亿元买，占比为15%。
- 主题指数ETF数量67只，规模为611亿元，占比为5%。
- Smart Beta ETF 35只，规模分别为344亿元，占比为3%。
- 增强指数ETF数量5只，规模为40亿元，占比为0.3%。

**手续费：**

参考华宝证券：ETF手续费万1，单笔最低0.2元