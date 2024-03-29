import backtrader as bt


class Ketler(bt.Indicator):
    """
    https://www.bilibili.com/video/BV1vT4y1M7B3
    这个是凯特勒指标的实现，是遵从了backtrader的指标实现
    """

    lines = ("expo", "atr", "upper", "lower")
    params = dict(ema=20, atr=17)
    plotinfo = dict(subplot=False)
    plotlines = dict(
        upper=dict(ls="--"), # 显示的时候，是一个虚线
        lower=dict(_samecolor=True)
    )

    def __init__(self):
        self.l.expo = bt.talib.EMA(self.datas[0].close, timeperiod=self.params.ema)
        self.l.atr = bt.talib.ATR(self.data.high,
                                  self.data.low,
                                  self.data.close,
                                  timeperiod=self.params.atr)
        self.l.upper = self.l.expo + self.l.atr
        self.l.lower = self.l.expo - self.l.atr
