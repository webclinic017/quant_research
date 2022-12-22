"""
为什么要做一个banker类呢？

因为，我定投的时候，投出去的钱，又收回来了，然后再投进去，来回往复，
就搞不清楚本金多少了？
所以，我设计一个banker，每次投，直到投到没钱了，就从银行里借，永远不用还，
这样从banker的视角，就知道到底投了多少钱了。
这样也有个细节问题，就是如果投出去的钱回来，可能也会被闲置，暂时忽略这点吧。
这个模拟，也比较接近于真实的投资，会从银转证不断地转钱进去，而不是一大笔只转一次。
"""


class Banker():
    def __init__(self):
        self.debt = 0
        self.debt_num = 0

    def credit(self,amount):
        self.debt += amount
        self.debt_num += 1
        return True