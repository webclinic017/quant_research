# encoding:gbk
import logging
import csv
import smtplib
from email.header import Header
from email.mime.text import MIMEText
from importlib import reload
import time
import requests
import yaml
import os
import traceback
import json

import dingtou
from dingtou.pyramid_v2.pyramid_v2_strategy import PyramidV2Strategy
from dingtou.pyramid_v2.position_calculator import PositionCalculator
from dingtou.utils.utils import str2date, date2str

import datetime

logger = logging.getLogger(__name__)

"""
# 实盘ETF定投策略：
    最终最优的参数组合是：7只股票，[-0.4~0.8]的上下买卖阈值，850日均线，买卖倍数为1:2 ==> 7%/年化（2013~2023）

# 版本维护：
- 2023.2.15 最后上线前的优化和调试，增加了plusplus发送，确认了前复权的正确性
- 2023.2.16 
    - 上线后异常修复，PyramidV2Strategy构造函数参数不匹配导致
    - 修改了提示，只提示缺少资金1次，用is_new_bar
- 2023.2.18
    - 增加了开盘、收盘发送一下仓位情况

运行回测的参数：
python -m dingtou.pyramid_v2.pyramid_v2 \
    -c 512690,512580,512660,159915,159928,510330,510500 \
    -s 20130101 \
    -e 20230101 \
    -b sh000001 \
    -a 0 \
    -m 850 \
    -ga 1000 \
    -gh 0.01 \
    -qn 0.4 \
    -qp 0.8 \
    -bf 1 \
    -sf 2 \
    -bk
"""

# 设置所有的参数，这些参数都是经过回测的最优的，无需调整（20230215更新）
stocks = ["512690.SH", "512580.SH", "512660.SH", "159915.SZ", "159928.SZ", "510330.SH", "510500.SH"]
class Args():
    grid_height = 0.01
    grid_amount = 1000
    quantile_positive = 0.8
    quantile_negative = 0.4
    ma = 850
    buy_factor = 1
    sell_factor = 2
args = Args()

# 设置所有的目录
home_dir = "c:\\workspace\\iquant"
log_dir = f"{home_dir}\\logs"
conf_path = f"{home_dir}\\config.yml"
data_dir = f"{home_dir}\\data"
trans_log = f"{data_dir}\\transaction.csv"
last_grid_position = f"{data_dir}\\last_grid_position.json"

POLICY_NAME = 'ETF定投'
MAX_TRADE_NUM_PER_DAY = 3  # 每天每只股票最大的交易次数（买和卖）
MIN_CASH = 80000  # 小于这个资金，就要报警了，防止资金不够，默认是300000比较合适，低于20万提醒，然后银转证到30万


def load_conf():
    f = open(conf_path, 'r', encoding='utf-8')
    result = f.read()
    return yaml.load(result, Loader=yaml.FullLoader)


conf = load_conf()


def _is_realtime(context):
    return not context.do_back_test


def init_logger(log_level=logging.DEBUG):
    if not os.path.exists(log_dir): os.makedirs(log_dir)

    file_name = time.strftime('%Y%m%d%H%M', time.localtime(time.time()))
    file_full_path = f"{log_dir}\\{file_name}.log"
    print("开始初始化日志：file=%r" % (file_full_path))

    root_logger = logging.getLogger()
    root_logger.setLevel(level=log_level)

    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d P%(process)d: %(message)s')

    stream_handler = logging.StreamHandler()
    root_logger.addHandler(stream_handler)
    print("日志：创建控制台处理器")

    t_handler = logging.FileHandler(file_full_path, encoding='utf-8')
    root_logger.addHandler(t_handler)
    print("日志：创建文件处理器", file_full_path)

    handlers = root_logger.handlers
    for handler in handlers:
        print(handler)
        handler.setLevel(level=log_level)
        handler.setFormatter(formatter)


class Broker():
    def __init__(self, account):
        self.context = None
        self.account = account

    def set_context(self, context):
        self.context = context

    def get_available_cash(self):
        account = get_trade_detail_data(self.account, A.acct_type, 'account')
        if len(account) == 0:
            raise Exception(f'账号{A.acct} 未登录 请检查')
        account = account[0]
        available_cash = int(account.m_dAvailable)
        return available_cash

    def check_max_trade(self, code):
        """
        为了防止程序有bug，导致1天内买入某只股票太多次，也是一种风控吧，
        限制一只股票买入次数。
        """
        # 这个函数只获得当天的订单，我测试的结果
        orders = get_trade_detail_data(self.account, 'stock', 'ORDER')
        counter = 0
        for order in orders:
            if order.m_strInstrumentID == code[:6]:
                counter += 1
        return counter > MAX_TRADE_NUM_PER_DAY

    def buy(self, code, date, amount=None, position=None):
        """
        http://docs.thinktrader.net/vip/pages/d0dd26/#_1-%E7%BB%BC%E5%90%88%E4%BA%A4%E6%98%93%E4%B8%8B%E5%8D%95-passorder
        passorder是对最后一根K线完全走完后生成的模型信号在下一根K线的第一个tick数据来时触发下单交易；
        采用quickTrade参数设置为1时，非历史bar上执行时（ContextInfo.is_last_bar()为True），只要策略模型中调用到就触发下单交易。
        quickTrade参数设置为2时，不判断bar状态，只要策略模型中调用到就触发下单交易，历史bar上也能触发下单，请谨慎使用。

        logger.debug("账号%s买入基金%s %.0f股",self.account,code,position)
        self.context.passorder(
         opType=23, # 股票买入，或沪港通、深港通股票买入
         orderType=1101, # 1101 单股、单账号、普通、股/手方式下单, 1102：单股、单账号、普通、金额（元）方式下单（只支持股票）
         accountid =self.account,
         orderCode = code,
         prType = 3, # 下单选价类型,4：卖1价；3：卖2价
         price = 0,
         volume = osition,  # 多少股/手：根据 orderType 值最后一位确定 volume 的单位：单股下单时：1：股 / 手
         quickTrade，int，设定是否立即触发下单，可选值：0：否1：是,passorder是对最后一根 K 线完全走完后生成的模型信号在下一根 K 线的第一个tick数据来时触发下单交易；采用quickTrade参数设置为1时，只要策略模型中调用到passorder交易函数就触发下单交易
         userOrderId，string，用户自设委托 ID，可缺省不写，写的时候必须把起前面的 strategyName 和 quickTrade 参数也填写。
                                对应 order 委托对象和 deal 成交对象中的 m_strRemark 属性，
                                通过 get_trade_detail_data 函数或委托主推函数 order_callback 和
                                成交主推函数 deal_callback 可拿到这两个对象信息。
         ContextInfo=self.context)
         无法写成这个参数形式，不知为何，只好写成不带参数提示类型的调用
        """
        # passorder(opType,orderType,accountid,orderCode,prType,price,volume,strategy_name,quickTrade,userOrderId,ContextInfo)
        # 按照股数（不是手数）进行下单，这个仅作参考用，不使用
        # passorder(23,1101, self.account, code, 3, 0, positoin, POLICY_NAME,1,order_id,self.context)
        # 按照钱数进行下单，但是因为A股有最少1手(100股)的限制，所以，函数会自动取整到100股的整数倍
        # passorder(23,1102, self.account, code, 3, 0, amount, POLICY_NAME,1,order_id,self.context)

        # 这个是风控和防止bug的需要，防止一天不停的买，每次查下当日成交订单，超过3次就不让挂单了
        if self.check_max_trade(code):
            msg = "挂买单失败，超过当日允许的最大交易次数[%d次]：账号%s于%s日按照卖2价，买入基金%s: %.0f元" % (
                MAX_TRADE_NUM_PER_DAY, self.account, date2str(date), code, amount)
            logger.info(msg)
            weixin('detail', msg)
            mail(f'[{POLICY_NAME}] 创建买单失败', msg)
            return False

        my_cash = self.get_available_cash()
        if my_cash < amount:
            msg = "挂买单失败，购买金额小于可用金额[%.2f]：账号%s于%s日按照卖2价，买入基金%s: %.0f元" % (
                my_cash, self.account, date2str(date), code, amount)
            logger.info(msg)
            weixin('detail', msg)
            mail(f'[{POLICY_NAME}] 创建买单失败', msg)
            plusplus_msg('创建买单', msg, 'error')
            return False

        old_postions = get_trade_detail_data(self.account, 'stock', 'position')
        order_time = time.strftime('%Y%m%d%H%M%S', time.localtime(time.time()))
        order_id = f"{order_time}_{code}_{POLICY_NAME}"

        # 23:股票;1102按金额买卖;3:卖2单；1:立刻生效
        passorder(23, 1102, self.account, code, 3, 0, amount, POLICY_NAME, 1, order_id, self.context)

        msg = "账号%s于%s日按照卖2价，买入基金%s: %.0f元" % (self.account, date2str(date), code, amount)
        logger.info(msg)
        weixin('detail', msg)
        mail(f'[{POLICY_NAME}] 创建买单(仅下单)', msg)
        plusplus_msg('创建买单', msg)

        postions = get_trade_detail_data(self.account, 'stock', 'position')

        time.sleep(1)  # 等1秒
        for p in old_postions:
            if p.m_strInstrumentID != code: continue
            # 买入前，打印一下旧的持仓
            logger.info("买入前，持仓：%s : %.0f股", p.m_strInstrumentID, p.m_nVolume)

        for p in postions:
            # 买入后，打印一下新的持仓
            if p.m_strInstrumentID != code: continue
            logger.info("买入后，持仓：%s : %.0f股", p.m_strInstrumentID, p.m_nVolume)
        return True

    def sell(self, code, date, amount=None, position=None):

        """
        卖出逻辑是仓位的多少

        passorder(
         opType = 24, # 24：股票卖出，或沪港通、深港通股票卖出
         orderType = 1102, # 单股、单账号、普通、金额（元）方式下单（只支持股票）
         accountid = self.account,
         orderCode = code,
         prType = 7, # 下单选价类型：6：买1价；7：买2价
         price = 0,
         volume = amount,
         ContextInfo= self.context )
        """

        # 这个是风控和防止bug的需要，防止一天不停的买，每次查下当日成交订单，超过3次就不让挂单了
        if self.check_max_trade(code):
            msg = "挂卖单失败，超过当日允许的最大交易次数[%d次]：账号%s于%s日按照买2价，买入基金%s: %.0f元" % (
                MAX_TRADE_NUM_PER_DAY, self.account, date2str(date), code, amount)
            logger.info(msg)
            weixin('detail', msg)
            mail(f'[{POLICY_NAME}] 创建卖单失败', msg)
            return False

        old_postions = postions = get_trade_detail_data(self.account, 'stock', 'position')
        available_amount = None
        for p in postions:
            # logger.debug("卖出：%s ：%.0f", p.m_strInstrumentID, p.m_nVolume)
            # code是510500.SH，但是m_strInstrumentID是510500，所以只取前6位
            if p.m_strInstrumentID == code[0:6] and p.m_dMarketValue < amount:
                available_amount = p.m_dMarketValue
            if p.m_strInstrumentID == code[0:6] and p.m_dMarketValue >= amount:
                available_amount = amount

        if available_amount is None:
            logger.warning("账号%s于%s日卖出基金%s %.0f元失败：没有持仓", self.account, date2str(date), code, amount)
            return False

        order_time = time.strftime('%Y%m%d%H%M%S', time.localtime(time.time()))
        order_id = f"{order_time}_{code}_{POLICY_NAME}"

        # 1102：使用金额方式卖出，买卖都是按照金额来的了
        # 按照买2价进行买入，没选买1，保险起见，quickTrade=1：可以立刻让订单生效，而不用等到bar的最后一个tick
        passorder(24, 1102, self.account, code, 7, 0, available_amount, POLICY_NAME, 1, order_id, self.context)

        msg = "账号%s于%s日按照买2价，卖出基金%s %.0f元，订单号[%s]" % (
            self.account, date2str(date), code, available_amount, order_id)
        logger.info(msg)
        weixin('detail', msg)
        mail(f'[{POLICY_NAME}] 创建卖单', msg)
        plusplus_msg('创建卖单', msg)

        postions = get_trade_detail_data(self.account, 'stock', 'position')

        time.sleep(1)  # 等1秒
        for p in old_postions:
            if p.m_strInstrumentID != code: continue
            # 买入前，打印一下旧的持仓
            logger.info("买入前，持仓：%s : %.0f股", p.m_strInstrumentID, p.m_nVolume)

        for p in postions:
            # 买入后，打印一下新的持仓
            if p.m_strInstrumentID != code: continue
            logger.info("买入后，持仓：%s : %.0f股", p.m_strInstrumentID, p.m_nVolume)
        return True

        return True


def plusplus_msg(title, msg, topic='signal'):
    try:
        # http://www.pushplus.plus/doc/guide/api.htm
        url = 'http://www.pushplus.plus/send'
        data = {
            "token": conf['plusplus']['token'],
            "title": title,
            "content": msg,
            "topic": topic
        }
        body = json.dumps(data).encode(encoding='utf-8')
        headers = {'Content-Type': 'application/json'}
        response = requests.post(url, data=body, headers=headers)
        data = response.json()
        if data and data.get("code", None) and data["code"] == 200:
            return
        if data and data.get("code", None):
            logger.warning("发往PlusPlus消息错误: code=%r, msg=%s, token=%s, topic=%s",
                           data['code'], data['msg'], conf['plusplus']['token'][:10] + "...", topic)
        else:
            logger.warning("发往PlusPlus消息错误: 返回为空")
    except Exception:
        logger.exception("发往PlusPlus消息发生异常", msg)
        return False


def mail(title, msg):
    uid = conf['email']['uid']
    pwd = conf['email']['pwd']
    host = conf['email']['host']
    email = conf['email']['email']

    subject = title
    receivers = [email]  # 接收邮件，可设置为你的QQ邮箱或者其他邮箱

    # 三个参数：第一个为文本内容，第二个 plain 设置文本格式，第三个 utf-8 设置编码
    message = MIMEText(msg, 'plain', 'utf-8')
    message['From'] = Header("量化机器人", 'utf-8')  # 发送者
    message['To'] = Header("量化机器人", 'utf-8')  # 接收者
    message['Subject'] = Header(subject, 'utf-8')

    try:
        # logger.info("发送邮件[%s]:[%s:%s]", host,uid,pwd)
        smtp = smtplib.SMTP_SSL(host)
        smtp.login(uid, pwd)
        smtp.sendmail(uid, receivers, message.as_string())
        logger.info("发往[%s]的邮件通知完成，标题：%s", email, title)
        return True
    except smtplib.SMTPException:
        logger.exception("发往[%s]的邮件出现异常，标题：%s", email, email)
        return False


def weixin(name, msg):
    """
    接口文档：https://developer.work.weixin.qq.com/document/path/91770?version=4.0.6.90540
    """
    logger.info("开始推送微信[类别:%s]消息", name)

    url = conf['weixin'][name]

    post_data = {
        "msgtype": "text",
        "text": {
            "content": msg[:2040]  # content    是    文本内容，最长不超过2048个字节，必须是utf8编码
        }
    }
    headers = {'Content-Type': 'application/json'}
    try:
        requests.post(url, json=post_data, headers=headers)
        logger.info("发往企业微信机器人[%s]的通知完成", name)
        return True
    except Exception:
        logger.exception("发往企业微信机器人[%s]的消息，发生异常", name)
        return False


# 创建空的类的实例 用来保存委托状态
# ContextInfo对象在盘中每次handlebar调用前都会被深拷贝,
# 如果调用handlebar的分笔不是k线最后分笔 ContextInfo会被回退到深拷贝的内容
# 所以ContextInfo不能用来记录快速交易的信号
class a():
    pass


A = a()


def init(ContextInfo):
    logger.info('策略开始初始化...')

    init_logger(logging.INFO)

    # 不知为何，实盘无法reload包
    if not _is_realtime(ContextInfo):
        reload(dingtou)
        reload(dingtou.pyramid_v2.pyramid_v2_strategy)
        reload(dingtou.utils.utils)
        logger.info("重新加载python包")

    if not os.path.exists(data_dir):
        os.makedirs(data_dir)

    A.acct = conf['account']  # 账号为模型交易界面选择账号
    A.acct_type = 'stock'  # 账号类型为模型交易界面选择账号
    A.stock_list = stocks
    A.data = {}

    ContextInfo.trade_code_list = stocks
    ContextInfo.set_universe(ContextInfo.trade_code_list)
    ContextInfo.set_account(A.acct)  # 之前未设置，导致deal_callback未回调，咨询了客服才想到
    ContextInfo.buy = True  # 必须要设置，否则，就不会触发买和卖，默认都是False
    ContextInfo.sell = True

    logger.info("设置股票池：%r", ContextInfo.trade_code_list)
    policy = PositionCalculator(args.grid_amount)

    A.broker = Broker(A.acct)
    A.strategy = PyramidV2Strategy(
        A.broker,
        args,
        last_grid_position  # 记录每只基金的最后的grid位置的json文件
    )
    logger.info('策略初始化完毕')


def get_last_price(ContextInfo, stock_code):
    """得到最后1分钟的价格(实盘)，或者最后1天的价格（回测）"""

    if _is_realtime(ContextInfo):
        period = '1m'  # 实盘的时候，取上一个bar的最后close的价格
    else:
        period = '1d'  # 模拟盘的时候，取上一天的close价格
    df = ContextInfo.get_market_data(
        fields=['close'],
        stock_code=[stock_code],
        count=1,
        period=period,
        dividend_type='front')# 必须前复权，后复权有重大问题，会导致偏离均线很大，导致错误交易,20230215

    logger.debug("获取[%s]%s日的(%s)价格:%.2f", stock_code, df.iloc[0].name, period, df.iloc[0].item())

    return df.iloc[0]


def deal_callback(ContextInfo, dealInfo):
    """
    交易成功的回调
    """
    _date = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    headers = ['证券代码', '买/卖', '合同编号', '成交日期', '成交时间', '成交价格', '成交数量', '手续费', '成交额',
               '备注']
    data = [dealInfo.m_strInstrumentID,
            dealInfo.m_nDirection,
            dealInfo.m_strOrderSysID,
            dealInfo.m_strTradeDate,
            dealInfo.m_strTradeTime,
            dealInfo.m_dPrice,
            dealInfo.m_nVolume,
            dealInfo.m_dComssion,
            dealInfo.m_dTradeAmount,
            dealInfo.m_strRemark]

    logger.info("交易成功：")
    logger.info(headers)
    logger.info(data)
    weixin('detail', f"[{POLICY_NAME}] 交易成功:\n{headers}\n{data}")
    mail(f'[{POLICY_NAME}] 交易成功', f"{headers}\n{data}")
    plusplus_msg('交易成功', f"{headers}\n{data}")

    flag_header = False
    if not os.path.exists(trans_log):
        flag_header = True

    with open(trans_log, "a") as f:
        writer = csv.writer(f, lineterminator="\n")
        if flag_header: writer.writerow(headers)
        writer.writerow(data)


def load_data(C, stock_code, today):
    df = A.data.get(stock_code, None)

    # 因为每分钟都会运行这个程序，所以为了性能，不是每分钟都加载，每天只加载一次
    if df is not None and df.iloc[-1].name == today:
        # logger.debug("[%s] %s日的数据，已经有了，无需再加载" , today, stock_code)
        # 有今天的日期，就啥都不做了
        return df

    # 如果和今天不一样，就需要重新加载数据
    start_date = str(C.get_open_date(stock_code))# 得到上市日期
    df = C.get_market_data(
        fields=['close'],
        stock_code=[stock_code],
        start_time=start_date,  # 必须要制定上市时间，否则，给我返回一堆的填充数，比如2019年上市，如果2400，返回2013的数，全是假的
        count=2400,  # 为了要找出很长的历史下的80%和20%分位数，需要加载十年的，其实只有8年的数据，因为有2年需要做移动平均，都是na
        period='1d',  # 这个会获得当天的信息
        dividend_type='front')  # 采用了前复权，主要是为了获得最新的价格
    df.to_csv(f"{data_dir}\\{stock_code}.csv")
    # 替换掉旧的数据
    A.data[stock_code] = df

    logger.info("加载%s日期%s~%s数据%d行", stock_code, df.iloc[0]._name, df.iloc[-1]._name, len(df))
    A.strategy.set_data(df_baseline=None, funds_dict=A.data)
    return df


def handlebar(ContextInfo):
    try:
        __handlebar(ContextInfo)
    except Exception as e:
        msg = ''.join(list(traceback.format_exc()))
        weixin('error', msg)
        mail(f'[{POLICY_NAME}] 发生异常错误', msg)
        plusplus_msg('发生异常', msg, 'error')
        logger.exception("handlerbar异常")

def get_account_info():
    result = ''
    account_info = get_trade_detail_data(A.acct, 'stock', 'account')
    for i in account_info:
        info = f'总资产:{i.m_dBalance},可用金额:{i.m_dAvailable},总市值:{i.m_dInstrumentValue},总盈亏:{round(i.m_dPositionProfit,2)}'
        result+=f'{info}\n'
    return result

def __handlebar(C):
    # 实盘/模拟盘的时候，从2015开始，所以需要跳过历史k线，
    # 回测的时候不需要
    if _is_realtime(C) and not C.is_last_bar():
        return

    # 获得当天的日期
    s = C.stockcode
    d = C.barpos
    t = C.get_bar_timetag(d)
    date = timetag_to_datetime(t, '%Y%m%d')

    # 跳过非交易时间
    now = datetime.datetime.now()
    now_time = now.strftime('%H%M%S')

    # 开盘后和收盘前，如果资金不足，就提醒，is_new_bar来提醒一次
    # 另外，必须是9:30分，因为生产环境下，handlebar 才会被触发，开盘前，不会运行handlebar的
    if _is_realtime(C) and C.is_new_bar() and (now_time[:4] == '0930' or now_time[:4] == "1458"):
        account = get_trade_detail_data(A.acct, A.acct_type, 'account')
        account = account[0]
        available_cash = int(account.m_dAvailable)

        # 每天开始和结束，都发送一遍我的资产信息
        account_information = get_account_info()
        logger.info("[%s] 发送账户信息：%s",now_time,account_information)
        weixin('detail', account_information)
        mail(f'[{POLICY_NAME}] 账户信息更新', account_information)
        plusplus_msg('账户信息更新', account_information)

        # logger.debug("交易日期: %s, 账号：%s,可用资金：%.2f",date, A.acct, available_cash)
        if available_cash < MIN_CASH:
            msg = "现金不足：当前现金 %.0f 元 < 最少的要求 %.0f 元，请补充现金" % (available_cash, MIN_CASH)
            logger.warning(msg)
            weixin('detail', msg)
            mail(f'[{POLICY_NAME}] 请补充现金', msg)
            plusplus_msg('请补充现金', msg)

    if _is_realtime(C) and (now_time < '093000' or now_time > "150000"):
        logger.warning("不在交易时间：%s", now_time)
        return

    """
    logger.debug("K线数量%d,bar的第一个tick:%r,K线号:%d,最后一个bar:%r",
        C.time_tick_size,
        C.is_new_bar(),
        C.barpos,
        C.is_last_bar())
    """

    # 注：在回测模式中，交易函数调用虚拟账号进行交易，在历史 K 线上记录买卖点，用以计算策略净值/
    # 回测指标；实盘运行调用策略中设置的资金账号进行交易，产生实际委托；模拟运行模式下交易函数无
    # 效。其中，can_cancel_order, cancel和do_order交易函数在回测模式中无实际意义，不建议使用。
    account = get_trade_detail_data(A.acct, A.acct_type, 'account')
    if len(account) == 0:
        logger.warning(f'账号{A.acct} 未登录 请检查')
        return

    # passorder(23,1101,A.acct,'588090.SH',3,0,100,C)
    for stock_code in A.stock_list:

        # 获得实盘上，最后一分钟的close的值
        series_last_price = get_last_price(C, stock_code)

        # 从series中，得到当天的日期
        today = series_last_price._name[:8]  # 获得当天的日期

        # 从series中，得到最后一分钟的价格
        last_price = series_last_price.item()

        # 判断是否需要重新加载数据，只有缓存的数据的最后日期和今天不一致的时候，才需要重新加载
        df = load_data(C, stock_code, today)

        # 得到最后一天的MA
        last_ma = df.iloc[-1].ma

        # 算出相差的百分比
        diff2last = (last_price - last_ma) / last_ma

        # 调试用
        A.broker.set_context(C)
        # last_price，是最后的后复权价格，注意是后复权
        msg = A.strategy.handle_one_fund(stock_code, str2date(date), last_price, last_ma, diff2last)

        if msg:
            weixin('detail', f"[{POLICY_NAME}] 触发交易:\n{msg}")
            mail(f'[{POLICY_NAME}] 触发交易', f"{msg}")
            plusplus_msg('策略触发交易', f"{msg}")





