class Trade:
    """
    用来定义一个交易
    """

    def __init__(self, code, target_date, amount, position, action):
        """
        买单，金额和份数二选一
        :param code:
        :param target_date:
        :param amount: 购买金额
        :param position: 购买的份数
        :param action:
        """
        self.code = code  # 基金代码
        self.target_date = target_date  # 预期成交日，往往是触发买/卖单的下一个交易日
        self.action = action  # buy|sell
        self.actual_date = None  # 实际成交日期，一般都会是target_date，除非遭遇停牌之类
        self.amount = amount  # 买了多少钱
        self.position = position  # 买了多少份
        self.price = -1  # 成交的价格

    def to_dict(self):
        return {
            'code': self.code,
            'target_date': self.target_date,
            'action': self.action,
            'actual_date': self.actual_date,
            'amount': self.amount,
            'position': self.position,
            'price': self.price
        }

    def __str__(self):
        return f"{self.code}/{self.target_date}/{self.action}/{self.position}/{self.price}"

    def __repr__(self):
        return self.__str__()
