# encoding:gbk
import datetime
import logging
import os
import traceback

import requests

from dingtou.utils.utils import load_conf

logger = logging.getLogger(__name__)

# �������е�Ŀ¼
home_dir = "c:\\workspace\\iquant"
log_dir = f"{home_dir}\\logs"
conf_path = f"{home_dir}\\config.yml"
data_dir = f"{home_dir}\\data"
trans_log = f"{data_dir}\\transaction.csv"
last_grid_position = f"{data_dir}\\last_grid_position.json"

POLICY_NAME = '����'

conf = load_conf(conf_path)


def init_logger(file_full_path, log_level=logging.DEBUG):
    if not os.path.exists(log_dir): os.makedirs(log_dir)
    print("��ʼ��ʼ����־��file=%r" % (file_full_path))
    root_logger = logging.getLogger()
    root_logger.setLevel(level=log_level)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d P%(process)d: %(message)s')

    stream_handler = logging.StreamHandler()
    root_logger.addHandler(stream_handler)
    print("��־����������̨������")

    t_handler = logging.FileHandler(file_full_path, encoding='utf-8')
    root_logger.addHandler(t_handler)
    print("��־�������ļ�������", file_full_path)

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
        r['���ʲ�'] = i.m_dBalance
        r['���ý��'] = i.m_dAvailable
        r['����ֵ'] = round(i.m_dInstrumentValue,4)
        r['��ӯ��'] = round(i.m_dPositionProfit,4)
        results.append(r)
    return results


def get_positions():
    results = []
    position_info = get_trade_detail_data(A.account, 'stock', 'position')
    for i in position_info:
        r = {}
        r['����'] = i.m_strInstrumentID
        r['����'] = i.m_strInstrumentName
        r['�г�'] = i.m_strExchangeName
        r['����'] = i.m_strOpenDate
        r['����'] = i.m_nVolume
        r['�ֲֳɱ�'] = round(i.m_dOpenPrice, 4)
        r['�ɱ���'] = round(i.m_dOpenCost, 4)
        r['���¼�'] = round(i.m_dSettlementPrice, 4)
        r['ӯ��'] = round(i.m_dFloatProfit, 4)
        r['��ֵ'] = round(i.m_dMarketValue, 4)
        r['ӯ������'] = round(i.m_dProfitRate, 4)
        results.append(r)
    return results


def get_deals():
    results = []
    deal_info = get_trade_detail_data(A.account, 'stock', 'DEAL')
    for i in deal_info:
        r = {}
        r['����'] = i.m_strInstrumentID
        r['����'] = i.m_strInstrumentName
        r['Ͷ�ʱ�ע'] = i.m_strRemark
        r['��ͬ���'] = i.m_strOrderSysID
        r['�������'] = i.m_nRef
        r['��Լ���'] = i.m_strCompactNo
        r['�ɽ�����'] = i.m_dPrice
        r['�ɽ���'] = i.m_nVolume
        r['�ɽ���'] = i.m_dTradeAmount
        r['����'] = i.m_strOptName
        r['ʱ��'] = i.m_strTradeTime
        r['����'] = i.m_strTradeDate

        results.append(r)
    return results


class a():
    pass


A = a()
A.account = conf['account']  # �˺�Ϊģ�ͽ��׽���ѡ���˺�
A.acct_type = 'stock'  # �˺�����Ϊģ�ͽ��׽���ѡ���˺�


def init(ContextInfo):
    init_logger(f"{log_dir}\\heartbeart.log", logging.DEBUG)
    logger.info('���Կ�ʼ��ʼ��...')

    account = get_trade_detail_data(A.account, A.acct_type, 'account')
    if len(account) == 0:
        raise Exception(f'�˺�{A.acct} δ��¼ ����')

    A.acct = conf['account']  # �˺�Ϊģ�ͽ��׽���ѡ���˺�
    A.acct_type = 'stock'  # �˺�����Ϊģ�ͽ��׽���ѡ���˺�
    ContextInfo.set_account(A.acct)  # ֮ǰδ���ã�����deal_callbackδ�ص�����ѯ�˿ͷ����뵽


def handlebar(ContextInfo):
    try:
        __handlebar(ContextInfo)
    except Exception as e:
        # msg = ''.join(list(traceback.format_exc()))
        logger.error("�쳣������%s", str(e))
        # logger.exception("handlerbar�쳣")


def http_json_post(url, dict_msg):
    logger.debug("��[%s]������Ϣ��%r", url, dict_msg)
    headers = {'Content-Type': 'application/json'}
    response = requests.post(url, json=dict_msg, headers=headers)
    logger.info('�ӿڷ���ԭʼ����:%r', response.text if len(response.text) < 50 else response.text[:50] + "......")
    data = response.json()
    logger.info('�ӿڷ���Json����:%r', data)
    return data


def __handlebar(C):
    if not C.is_last_bar(): return
    if not C.is_new_bar(): return

    # ��õ��������
    s = C.stockcode
    d = C.barpos
    t = C.get_bar_timetag(d)
    date = timetag_to_datetime(t, '%Y%m%d')

    # �����ǽ���ʱ��
    now = datetime.datetime.now()
    now_time = now.strftime('%H%M%S')

    """
    logger.debug("K������%d,bar�ĵ�һ��tick:%r,K�ߺ�:%d,���һ��bar:%r",
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
