from utils.utils import date2str


class Position:
    """
    用来定义持有的仓位
    """

    def __init__(self, code, position, price, create_date):
        self.code = code  # 基金代码
        self.position = position  # 初始仓位
        self.create_date = create_date
        self.update_date = create_date
        self.cost = price  # 初始成本

    def update(self, date, position, price):
        self.update_date = date

        # 买入才更新持仓成本
        if position > 0:
            # 更新新成本和仓位
            old_value = self.position * self.cost # 旧价值
            new_value = old_value + position * price # 今天新买入的价值 + 旧价值
            self.position += position
            self.cost = new_value / self.position
        else:
            self.position += position

    def to_dict(self):
        return {
            'code': self.code,
            'update_date': date2str(self.update_date),
            'cost': self.cost,
            'position': self.position,
            'cost_amount': self.cost * self.position
        }
