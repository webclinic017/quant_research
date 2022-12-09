"""
情景：
当你多次买入、又卖出的时候，且，每次的金额是不定的时候，
你是否还能搞清楚以下问题：
- 我到底投了多少本金
- 我到底获得了多少收益

问题1：
你可能说，我所有产出就是：所有的卖出金额+股市市值，我所有的投入就是：所有的买入金额，
错！
你其实没有投入那么多资金，你不能把每次投入都算到里面去，我举个极端例子：
我投入10000，结果进了股市，赚了10000，我全部卖出这20000市值，
然后我又把这20000，再次投入股市，然后又赚了，全部卖出，收获40000。
如果是按上面说的，我投入了10000+20000 = 30000，我产出是20000+40000 = 60000，
那我的收益率就是 200%，
错了！
我实际就是投入了10000，最终我重复利用我的资金，收获了40000，我的收益率是400%。
所以，我其实是低估了我的收益。

问题2：
如果我一共有10万，我只拿了1万，就赚到了4万，我的资金利用率是10%，这个太低了。
所以，我得明确知道到底动用了我多少本金，我才能算清楚我的资金利用率。
但是，上面的例子比较简单，就是1万元反复投入到股市里面去了。
但是，如果我不是这样呢？
比如我投入1万，赚了，股市里现在是2万的市值，且，我套现了5000出来，
然后，我有投入了1万，那么，很明显，这1万里，既有我套现的5000，又有我额外投入的5000，
所以，你一共投入了1+0.5=1.5万的本金，
然后，我继续玩这个投资游戏，来来往往的，你还能清楚的计算清楚你的投入本金么？
你无法清楚地计算清楚，你就无法计算清楚你对这个投资标的的资金利用率。

那么，应该如何计算呢？

我先说结论：
- 投入的资金是：x0 + sum(x1~xn) - sum(y0~y_n-1)
- 获得产出是（不是收益）：sum(y0~y_n-1) - sum(x1~xn) + yn + stock

我来详细解释一下，考虑以下场景，我每次买入xi，卖出为yi，中间的钱沉淀在股市中，体现为市值：

买入   买出
=========
x0---->y0
x1---->y1
x2---->y2
.....
xn---->yn

那么，我其实总投入为：
    总共投入资金：x0 + x1-y0 + x2 - y1 + ... + xn - y_n-1
那么，我其实总产出为：
    总共产出：y0-x1 +  y1-x2 + .... + y_n-1 - xn   +   y_n   +    stock市值
    解释下总产出：
        以第一次为例子，投入x0，产出是股市市值 + y0，
        但是y0不是产出，因为你后续有用y0的再投入股市了，即x1中包含了y0，
        所以y0中药刨除x1，
        但是你担心如果额外扣除了了咋办？举例，我上次y0卖出了10000元，然后我下次买入x1为20000元，
        那么y0的产出就是变成了y0-x1=10000-20000=-10000，
        -10000就负10000，没关系，产出确实是负的啊。

invest = x_0 + \sum_{i=1}^nx_i - \sum_{j=0}^{n-1}y_i
yield = x_0 + \sum_{j=0}^{n-1}y_i - \sum_{i=1}^nx_i + y_n + stock

===========================================

上述算是错的，正确的是：
x0---->y0
x1---->y1
x2---->y2
.....
xn---->yn
算投入：只有x1-y0>0，才计入投资，x2-y1也是这样算，。。。，所以最终是 x0 + 所有(xi - y_i-1)大于0的
算产出：只有y0-x1>0，才计入产出，y1-x2也是这样算，。。。，最终是，yn + 所有(y_i-1 - x)大于0的 + 持仓市值
这个算法是对的，
但是！但是！
实现的时候，可能不是买、卖、买、卖、买、卖、买、卖，交替进行的，
而可能是买买买、卖卖、买、卖卖卖。。。,进行的，
这样还得合并买和卖，变成买卖交替，再走上面的算法。

我靠！太烦了，放弃了。

我不考察单个产品的收益了。

但是，单个资金的投入，还是可以用的。

<df_trade>
{
    'code': self.code,
    'target_date': self.target_date,
    'action': self.action,
    'actual_date': self.actual_date,
    'amount': self.amount,
    'position': self.position,
    'price': self.price
}
"""


def calculate(df_trade, broker, code=None):
    """
    用于计算
    :param df_trades:
    :return:
    """
    # 先按照时间排序
    df = df_trade.sort_values(by='actual_date')

    # 如果提供了基金代码，就是来考察这只基金的投入资金情况，否则，是整体投资的情况
    if code: df = df[df_trade.code == code]

    df_buy = df[df.action == 'buy']
    df_sell = df[df.action == 'sell']

    if len(df_buy)==0: return 0,None,None
    buy_0 = df_buy.iloc[0].amount
    buy_sum_1_n = df_buy.iloc[1:].amount.sum()

    if len(df_sell)==0: return buy_0+buy_sum_1_n,None,None
    sell_n = df_sell.iloc[-1].amount
    sell_sum_0_n_1 = df_sell.iloc[:-1].amount.sum()

    # - 投入的资金是：x0 + sum(x1~xn) - sum(y0~y_n-1)
    invest = buy_0 + buy_sum_1_n - sell_sum_0_n_1

    # 持仓市值
    position_value = broker.get_total_position_value()
    if code: position_value = broker.get_position_value(code)

    # - 获得产出是（不是收益）：sum(y0~y_n-1) - sum(x1~xn) + yn + stock
    _yield = sell_sum_0_n_1 - buy_sum_1_n + sell_n + position_value


    # 收益为
    if invest > 0:
        _return = (_yield - invest) / invest
    else:
        _return = (_yield - invest) / invest

    return invest, _yield, _return # 目前只有invest在用

