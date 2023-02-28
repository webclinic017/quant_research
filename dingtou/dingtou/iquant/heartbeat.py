# encoding:gbk
import datetime
import logging
import os
import traceback

import requests

from dingtou.utils.utils import load_conf

logger = logging.getLogger(__name__)

# 设置所有的目录
home_dir = "c:\\workspace\\iquant"
log_dir = f"{home_dir}\\logs"
conf_path = f"{home_dir}\\config.yml"
data_dir = f"{home_dir}\\data"
trans_log = f"{data_dir}\\transaction.csv"
last_grid_position = f"{data_dir}\\last_grid_position.json"

POLICY_NAME = '心跳'

conf = load_conf(conf_path)


def init_logger(file_full_path, log_level=logging.DEBUG):
    if not os.path.exists(log_dir): os.makedirs(log_dir)
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


def get_accounts():
    results = []
    account_info = get_trade_detail_data(A.account, 'stock', 'account')
    for i in account_info:
        r = {}
        r['总资产'] = i.m_dBalance
        r['可用金额'] = i.m_dAvailable
        r['总市值'] = round(i.m_dInstrumentValue,4)
        r['总盈亏'] = round(i.m_dPositionProfit,4)
        results.append(r)
    return results


def get_positions():
    results = []
    position_info = get_trade_detail_data(A.account, 'stock', 'position')
    for i in position_info:
        r = {}
        r['代码'] = i.m_strInstrumentID
        r['名称'] = i.m_strInstrumentName
        r['市场'] = i.m_strExchangeName
        r['日期'] = i.m_strOpenDate
        r['股数'] = i.m_nVolume
        r['持仓成本'] = round(i.m_dOpenPrice, 4)
        r['成本价'] = round(i.m_dOpenCost, 4)
        r['最新价'] = round(i.m_dSettlementPrice, 4)
        r['盈亏'] = round(i.m_dFloatProfit, 4)
        r['市值'] = round(i.m_dMarketValue, 4)
        r['盈亏比例'] = round(i.m_dProfitRate, 4)
        results.append(r)
    return results


def get_deals():
    results = []
    deal_info = get_trade_detail_data(A.account, 'stock', 'DEAL')
    for i in deal_info:
        r = {}
        r['代码'] = i.m_strInstrumentID
        r['名称'] = i.m_strInstrumentName
        r['投资备注'] = i.m_strRemark
        r['合同编号'] = i.m_strOrderSysID
        r['订单编号'] = i.m_nRef
        r['合约编号'] = i.m_strCompactNo
        r['成交均价'] = i.m_dPrice
        r['成交量'] = i.m_nVolume
        r['成交额'] = i.m_dTradeAmount
        r['买卖'] = i.m_strOptName
        r['时间'] = i.m_strTradeTime
        r['日期'] = i.m_strTradeDate

        results.append(r)
    return results


class a():
    pass


A = a()
A.account = conf['account']  # 账号为模型交易界面选择账号
A.acct_type = 'stock'  # 账号类型为模型交易界面选择账号


def init(ContextInfo):
    init_logger(f"{log_dir}\\heartbeart.log", logging.DEBUG)
    logger.info('策略开始初始化...')

    account = get_trade_detail_data(A.account, A.acct_type, 'account')
    if len(account) == 0:
        raise Exception(f'账号{A.acct} 未登录 请检查')

    A.acct = conf['account']  # 账号为模型交易界面选择账号
    A.acct_type = 'stock'  # 账号类型为模型交易界面选择账号
    ContextInfo.set_account(A.acct)  # 之前未设置，导致deal_callback未回调，咨询了客服才想到


def handlebar(ContextInfo):
    try:
        __handlebar(ContextInfo)
    except Exception as e:
        # msg = ''.join(list(traceback.format_exc()))
        logger.error("异常发生：%s", str(e))
        # logger.exception("handlerbar异常")


def http_json_post(url, dict_msg):
    logger.debug("向[%s]推送消息：%r", url, dict_msg)
    headers = {'Content-Type': 'application/json'}
    response = requests.post(url, json=dict_msg, headers=headers)
    logger.info('接口返回原始报文:%r', response.text if len(response.text) < 50 else response.text[:50] + "......")
    data = response.json()
    logger.info('接口返回Json报文:%r', data)
    return data


def __handlebar(C):
    if not C.is_last_bar(): return
    if not C.is_new_bar(): return

    # 获得当天的日期
    s = C.stockcode
    d = C.barpos
    t = C.get_bar_timetag(d)
    date = timetag_to_datetime(t, '%Y%m%d')

    # 跳过非交易时间
    now = datetime.datetime.now()
    now_time = now.strftime('%H%M%S')

    """
    logger.debug("K线数量%d,bar的第一个tick:%r,K线号:%d,最后一个bar:%r",
        C.time_tick_size,
        C.is_new_bar(),
        C.barpos,
        C.is_last_bar())
    """

    http_json_post(conf['url'], {'action': 'heartbeat',
                                 'name': 'qmt',
                                 'info': [
                                     {'name': 'accounts', 'data': get_accounts()},
                                     {'name': 'positions', 'data': get_positions()},
                                     {'name': 'deals', 'data': get_deals()}
                                 ]})
