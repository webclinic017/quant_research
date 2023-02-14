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

import dingtou
from dingtou.pyramid_v2.pyramid_v2_strategy import PyramidV2Strategy
from dingtou.pyramid_v2.position_calculator import PositionCalculator
from dingtou.utils.utils import str2date, date2str

import datetime

logger = logging.getLogger(__name__)

# �������еĲ�������Щ�������Ǿ����ز�����ŵģ��������
# stocks = ['510500.SH','510330.SH','159915.SZ','588090.SH']
stocks = ['588090.SH']  # TODO����ʱ����һֻ����
grid_height = 0.01
grid_amount = 3000  # 3000Ԫ�ȽϺ��ʣ���Լ115w/year��һ��Ͷ6.7�����һ��24�򣬳���30�򣬵���20��ͱ�����ETF��Ͷ����ͳ�ơ�
quantile_positive = 0.8
quantile_negative = 0.2
ma_days = 850

# �������е�Ŀ¼
home_dir = "c:\\workspace\\iquant"
log_dir = f"{home_dir}\\logs"
conf_path = f"{home_dir}\\config.yml"
trans_log_dir = f"{home_dir}\\history"
trans_log = f"{trans_log_dir}\\transaction.csv"
last_grid_position = f"{trans_log_dir}\\last_grid_position.json"

POLICY_NAME = 'ETF��Ͷ'
MAX_TRADE_NUM_PER_DAY = 3  # ÿ��ÿֻ��Ʊ���Ľ��״������������
MIN_CASH = 200000  # С������ʽ𣬾�Ҫ�����ˣ���ֹ�ʽ𲻹�


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


class Broker():
    def __init__(self, account):
        self.context = None
        self.account = account

    def set_context(self, context):
        self.context = context

    def get_available_cash(self):
        account = get_trade_detail_data(self.account, A.acct_type, 'account')
        if len(account) == 0:
            raise Exception(f'�˺�{A.acct} δ��¼ ����')
        account = account[0]
        available_cash = int(account.m_dAvailable)
        return available_cash

    def check_max_trade(self, code):
        """
        Ϊ�˷�ֹ������bug������1��������ĳֻ��Ʊ̫��Σ�Ҳ��һ�ַ�ذɣ�
        ����һֻ��Ʊ���������
        """
        # �������ֻ��õ���Ķ������Ҳ��ԵĽ��
        orders = get_trade_detail_data(self.account, 'stock', 'ORDER')
        counter = 0
        for order in orders:
            if order.m_strInstrumentID == code[:6]:
                counter += 1
        return counter > MAX_TRADE_NUM_PER_DAY

    def buy(self, code, date, amount=None, position=None):
        """
        http://docs.thinktrader.net/vip/pages/d0dd26/#_1-%E7%BB%BC%E5%90%88%E4%BA%A4%E6%98%93%E4%B8%8B%E5%8D%95-passorder
        passorder�Ƕ����һ��K����ȫ��������ɵ�ģ���ź�����һ��K�ߵĵ�һ��tick������ʱ�����µ����ף�
        ����quickTrade��������Ϊ1ʱ������ʷbar��ִ��ʱ��ContextInfo.is_last_bar()ΪTrue����ֻҪ����ģ���е��õ��ʹ����µ����ס�
        quickTrade��������Ϊ2ʱ�����ж�bar״̬��ֻҪ����ģ���е��õ��ʹ����µ����ף���ʷbar��Ҳ�ܴ����µ��������ʹ�á�

        logger.debug("�˺�%s�������%s %.0f��",self.account,code,position)
        self.context.passorder(
         opType=23, # ��Ʊ���룬�򻦸�ͨ�����ͨ��Ʊ����
         orderType=1101, # ���ɡ����˺š���ͨ����/�ַ�ʽ�µ�,
         accountid =self.account,
         orderCode = code,
         prType = 3, # �µ�ѡ������,4����1�ۣ�3����2��
         price = 0,
         volume = osition,  # ���ٹ�/�֣����� orderType ֵ���һλȷ�� volume �ĵ�λ�������µ�ʱ��1���� / ��
         quickTrade��int���趨�Ƿ����������µ�����ѡֵ��0����1����,passorder�Ƕ����һ�� K ����ȫ��������ɵ�ģ���ź�����һ�� K �ߵĵ�һ��tick������ʱ�����µ����ף�����quickTrade��������Ϊ1ʱ��ֻҪ����ģ���е��õ�passorder���׺����ʹ����µ�����
         userOrderId��string���û�����ί�� ID����ȱʡ��д��д��ʱ��������ǰ��� strategyName �� quickTrade ����Ҳ��д��
                                ��Ӧ order ί�ж���� deal �ɽ������е� m_strRemark ���ԣ�
                                ͨ�� get_trade_detail_data ������ί�����ƺ��� order_callback ��
                                �ɽ����ƺ��� deal_callback ���õ�������������Ϣ��
         ContextInfo=self.context)
         �޷�д�����������ʽ����֪Ϊ�Σ�ֻ��д�ɲ���������ʾ���͵ĵ���
        """
        # passorder(opType,orderType,accountid,orderCode,prType,price,volume,strategy_name,quickTrade,userOrderId,ContextInfo)

        # ���չ��������������������µ�
        # passorder(23,1101, self.account, code, 3, 0, positoin, POLICY_NAME,1,order_id,self.context)

        # ����Ǯ�������µ���������ΪA��������1��(100��)�����ƣ����ԣ��������Զ�ȡ����100�ɵ�������
        # passorder(23,1102, self.account, code, 3, 0, amount, POLICY_NAME,1,order_id,self.context)

        # ����Ƿ�غͷ�ֹbug����Ҫ����ֹһ�첻ͣ����ÿ�β��µ��ճɽ�����������3�ξͲ��ùҵ���
        if self.check_max_trade(code):
            msg = "����ʧ�ܣ�������������������״���[%d��]���˺�%s��%s�հ�����2�ۣ��������%s: %.0fԪ" % (
            MAX_TRADE_NUM_PER_DAY, self.account, date2str(date), code, amount)
            logger.info(msg)
            weixin('detail', msg)
            mail(f'[{POLICY_NAME}] ������ʧ��', msg)
            return False

        my_cash = self.get_available_cash()
        if my_cash < amount:
            msg = "����ʧ�ܣ�������С�ڿ��ý��[%.2f]���˺�%s��%s�հ�����2�ۣ��������%s: %.0fԪ" % (
            my_cash, self.account, date2str(date), code, amount)
            logger.info(msg)
            weixin('detail', msg)
            mail(f'[{POLICY_NAME}] ������ʧ��', msg)
            return False

        old_postions = get_trade_detail_data(self.account, 'stock', 'position')
        order_time = time.strftime('%Y%m%d%H%M%S', time.localtime(time.time()))
        order_id = f"{order_time}_{code}_{POLICY_NAME}"

        # ���԰��ռ۸���,110Ԫ
        # passorder(23,1102, self.account, code, 3, 0, 110, POLICY_NAME,1,order_id,self.context)

        msg = "�˺�%s��%s�հ�����2�ۣ��������%s: %.0fԪ" % (self.account, date2str(date), code, amount)
        logger.info(msg)
        weixin('detail', msg)
        mail(f'[{POLICY_NAME}] ������(���µ�)', msg)

        postions = get_trade_detail_data(self.account, 'stock', 'position')
        for p in old_postions:
            # ����ǰ����ӡһ�¾ɵĳֲ�
            logger.info("����ǰ���ֲ֣�%s : %.0f��", p.m_strInstrumentID, p.m_nVolume)
        for p in postions:
            # ����󣬴�ӡһ���µĳֲ�
            logger.info("����󣬳ֲ֣�%s : %.0f��", p.m_strInstrumentID, p.m_nVolume)
        return True

    def sell(self, code, date, amount=None, position=None):

        """
        �����߼��ǲ�λ�Ķ���

        passorder(
         opType = 24, # 24����Ʊ�������򻦸�ͨ�����ͨ��Ʊ����
         orderType = 1101, # ���ɡ����˺š���ͨ����/�ַ�ʽ�µ�,
         accountid = self.account,
         orderCode = code,
         prType = 7, # �µ�ѡ�����ͣ�6����1�ۣ�7����2��
         price = 0,
         volume = position,
         ContextInfo= self.context )
        """

        # ����Ƿ�غͷ�ֹbug����Ҫ����ֹһ�첻ͣ����ÿ�β��µ��ճɽ�����������3�ξͲ��ùҵ���
        if self.check_max_trade(code):
            msg = "������ʧ�ܣ�������������������״���[%d��]���˺�%s��%s�հ�����2�ۣ��������%s: %.0fԪ" % (
            MAX_TRADE_NUM_PER_DAY, self.account, date2str(date), code, amount)
            logger.info(msg)
            weixin('detail', msg)
            mail(f'[{POLICY_NAME}] ��������ʧ��', msg)
            return False

        postions = get_trade_detail_data(self.account, 'stock', 'position')
        available_position = None
        for p in postions:
            # logger.debug("������%s ��%.0f", p.m_strInstrumentID, p.m_nVolume)
            # code��510500.SH������m_strInstrumentID��510500������ֻȡǰ6λ
            if p.m_strInstrumentID == code[0:6] and p.m_nVolume < position:
                available_position = p.m_nVolume
            if p.m_strInstrumentID == code[0:6] and p.m_nVolume >= position:
                available_position = position

        if available_position is None:
            logger.warning("�˺�%s��%s����������%s %.0f��ʧ�ܣ�û�гֲ�", self.account, date2str(date), code, position)
            return False

        old_postions = get_trade_detail_data(self.account, 'stock', 'position')
        order_time = time.strftime('%Y%m%d%H%M%S', time.localtime(time.time()))
        order_id = f"{order_time}_{code}_{POLICY_NAME}"

        # ������2�۽������룬ûѡ��1���������
        passorder(24, 1101, self.account, code, 7, 0, available_position, POLICY_NAME, 1, order_id, self.context)

        msg = "�˺�%s��%s�հ�����2�ۣ���������%s %.0f��" % (self.account, date2str(date), code, available_position)
        logger.info(msg)
        weixin('detail', msg)
        mail(f'[{POLICY_NAME}] ��������', msg)

        postions = get_trade_detail_data(self.account, 'stock', 'position')
        for p in postions:
            # ����󣬴�ӡһ���µĳֲ�
            logger.info("�����󣬳ֲ֣�%s : %.0f��", p.m_strInstrumentID, p.m_nVolume)

        return True


def mail(title, msg):
    uid = conf['email']['uid']
    pwd = conf['email']['pwd']
    host = conf['email']['host']
    email = conf['email']['email']

    subject = title
    receivers = [email]  # �����ʼ���������Ϊ���QQ���������������

    # ������������һ��Ϊ�ı����ݣ��ڶ��� plain �����ı���ʽ�������� utf-8 ���ñ���
    message = MIMEText(msg, 'plain', 'utf-8')
    message['From'] = Header("����������", 'utf-8')  # ������
    message['To'] = Header("����������", 'utf-8')  # ������
    message['Subject'] = Header(subject, 'utf-8')

    try:
        # logger.info("�����ʼ�[%s]:[%s:%s]", host,uid,pwd)
        smtp = smtplib.SMTP_SSL(host)
        smtp.login(uid, pwd)
        smtp.sendmail(uid, receivers, message.as_string())
        logger.info("����[%s]���ʼ�֪ͨ��ɣ����⣺%s", email, title)
        return True
    except smtplib.SMTPException:
        logger.exception("����[%s]���ʼ������쳣�����⣺%s", email, email)
        return False


def weixin(name, msg):
    """
    �ӿ��ĵ���https://developer.work.weixin.qq.com/document/path/91770?version=4.0.6.90540
    """
    logger.info("��ʼ����΢��[���:%s]��Ϣ", name)

    url = conf['weixin'][name]

    post_data = {
        "msgtype": "text",
        "text": {
            "content": msg[:2040]  # content    ��    �ı����ݣ��������2048���ֽڣ�������utf8����
        }
    }
    headers = {'Content-Type': 'application/json'}
    try:
        requests.post(url, json=post_data, headers=headers)
        logger.info("������ҵ΢�Ż�����[%s]��֪ͨ���", name)
        return True
    except Exception:
        logger.exception("������ҵ΢�Ż�����[%s]����Ϣ�������쳣", name)
        return False


# �����յ����ʵ�� ��������ί��״̬
# ContextInfo����������ÿ��handlebar����ǰ���ᱻ���,
# �������handlebar�ķֱʲ���k�����ֱ� ContextInfo�ᱻ���˵����������
# ����ContextInfo����������¼���ٽ��׵��ź�
class a():
    pass


A = a()


def init(ContextInfo):
    logger.info('���Կ�ʼ��ʼ��...')

    init_logger(logging.DEBUG)

    # ��֪Ϊ�Σ�ʵ���޷�reload��
    if not _is_realtime(ContextInfo):
        reload(dingtou)
        reload(dingtou.pyramid_v2.pyramid_v2_strategy)
        reload(dingtou.utils.utils)
        logger.info("���¼���python��")

    if not os.path.exists(trans_log_dir):
        os.makedirs(trans_log_dir)

    A.acct = conf['account']  # �˺�Ϊģ�ͽ��׽���ѡ���˺�
    A.acct_type = 'stock'  # �˺�����Ϊģ�ͽ��׽���ѡ���˺�
    A.stock_list = stocks
    A.data = {}

    ContextInfo.trade_code_list = stocks
    ContextInfo.set_universe(ContextInfo.trade_code_list)
    ContextInfo.set_account(A.acct)  # ֮ǰδ���ã�����deal_callbackδ�ص�����ѯ�˿ͷ����뵽
    ContextInfo.buy = True  # ����Ҫ���ã����򣬾Ͳ��ᴥ���������Ĭ�϶���False
    ContextInfo.sell = True

    logger.info("���ù�Ʊ�أ�%r", ContextInfo.trade_code_list)
    policy = PositionCalculator(grid_amount)

    A.broker = Broker(A.acct)
    A.strategy = PyramidV2Strategy(
        A.broker,
        policy,
        grid_height,
        quantile_positive,
        quantile_negative,
        ma_days,
        None,
        last_grid_position  # ��¼ÿֻ���������gridλ�õ�json�ļ�
    )
    logger.info('���Գ�ʼ�����')


def get_last_price(ContextInfo, stock_code):
    """�õ����1���ӵļ۸�(ʵ��)���������1��ļ۸񣨻ز⣩"""

    if _is_realtime(ContextInfo):
        period = '1m'  # ʵ�̵�ʱ��ȡ��һ��bar�����close�ļ۸�
    else:
        period = '1d'  # ģ���̵�ʱ��ȡ��һ���close�۸�
    df = ContextInfo.get_market_data(
        fields=['close'],
        stock_code=[stock_code],
        count=1,
        period=period,
        dividend_type='back')

    logger.debug("��ȡ[%s]%s�յ�(%s)�۸�:%.2f", stock_code, df.iloc[0].name, period, df.iloc[0].item())

    return df.iloc[0]


def deal_callback(ContextInfo, dealInfo):
    """
    ���׳ɹ��Ļص�
    """
    _date = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    headers = ['֤ȯ����', '��/��', '��ͬ���', '�ɽ�����', '�ɽ�ʱ��', '�ɽ��۸�', '�ɽ�����', '������', '�ɽ���',
               '��ע']
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

    logger.info("���׳ɹ���")
    logger.info(headers)
    logger.info(data)
    weixin('detail', f"[{POLICY_NAME}] �������:\n{headers}\n{data}")
    mail(f'[{POLICY_NAME}] ���׳ɹ����', f"{headers}\n{data}")

    flag_header = False
    if not os.path.exists(trans_log):
        flag_header = True

    with open(trans_log, "a") as f:
        writer = csv.writer(f, lineterminator="\n")
        if flag_header: writer.writerow(headers)
        writer.writerow(data)


def load_data(C, stock_code, today):
    df = A.data.get(stock_code, None)

    # ��Ϊÿ���Ӷ������������������Ϊ�����ܣ�����ÿ���Ӷ����أ�ÿ��ֻ����һ��
    if df is not None and df.iloc[-1].name == today:
        # logger.debug("[%s] %s�յ����ݣ��Ѿ����ˣ������ټ���" , today, stock_code)
        # �н�������ڣ���ɶ��������
        return df

    # ����ͽ��첻һ��������Ҫ���¼�������
    df = C.get_market_data(
        fields=['close'],
        stock_code=[stock_code],
        count=2400,  # Ϊ��Ҫ�ҳ��ܳ�����ʷ�µ�80%��20%��λ������Ҫ����ʮ��ģ���ʵֻ��8������ݣ���Ϊ��2����Ҫ���ƶ�ƽ��������na
        period='1d',  # ������õ������Ϣ
        dividend_type='front')  # ������ǰ��Ȩ����Ҫ��Ϊ�˻�����µļ۸�
    # �滻���ɵ�����
    A.data[stock_code] = df

    logger.info("����%s����%s~%s����%d��", stock_code, df.iloc[0]._name, df.iloc[-1]._name, len(df))
    A.strategy.set_data(df_baseline=None, funds_dict=A.data)
    return df


def handlebar(ContextInfo):
    try:
        __handlebar(ContextInfo)
    except Exception as e:
        msg = ''.join(list(traceback.format_exc()))
        weixin('error', msg)
        mail(f'[{POLICY_NAME}] �����쳣����', msg)
        logger.exception("handlerbar�쳣")


def __handlebar(C):
    # ʵ��/ģ���̵�ʱ�򣬴�2015��ʼ��������Ҫ������ʷk�ߣ�
    # �ز��ʱ����Ҫ
    if _is_realtime(C) and not C.is_last_bar():
        return

    # ��õ��������
    s = C.stockcode
    d = C.barpos
    t = C.get_bar_timetag(d)
    date = timetag_to_datetime(t, '%Y%m%d')

    # �����ǽ���ʱ��
    now = datetime.datetime.now()
    now_time = now.strftime('%H%M%S')
    if _is_realtime(C) and (now_time < '093000' or now_time > "150000"):
        logger.warning("���ڽ���ʱ�䣺%s", now_time)
        # TODO��ע�͵����������
        return

    """
    logger.debug("K������%d,bar�ĵ�һ��tick:%r,K�ߺ�:%d,���һ��bar:%r",
        C.time_tick_size,
        C.is_new_bar(),
        C.barpos,
        C.is_last_bar())
    """

    # ע���ڻز�ģʽ�У����׺������������˺Ž��н��ף�����ʷ K ���ϼ�¼�����㣬���Լ�����Ծ�ֵ/
    # �ز�ָ�ꣻʵ�����е��ò��������õ��ʽ��˺Ž��н��ף�����ʵ��ί�У�ģ������ģʽ�½��׺�����
    # Ч�����У�can_cancel_order, cancel��do_order���׺����ڻز�ģʽ����ʵ�����壬������ʹ�á�
    account = get_trade_detail_data(A.acct, A.acct_type, 'account')
    if len(account) == 0:
        logger.warning(f'�˺�{A.acct} δ��¼ ����')
        return

    # ���̺������ǰ������ʽ��㣬������
    if _is_realtime(C) and (now_time[:4] == '0931' or now_time[:4] == "1459"):
        account = account[0]
        available_cash = int(account.m_dAvailable)
        # logger.debug("��������: %s, �˺ţ�%s,�����ʽ�%.2f",date, A.acct, available_cash)
        if available_cash < MIN_CASH:
            msg = "�ֽ��㣺��ǰ�ֽ� %.0f Ԫ < ���ٵ�Ҫ�� %.0f Ԫ" % (available_cash, MIN_CASH)
            logger.warning(msg)
            weixin('detail', msg)
            mail(f'[{POLICY_NAME}] �벹���ֽ�', msg)

    # passorder(23,1101,A.acct,'588090.SH',3,0,100,C)
    for stock_code in A.stock_list:

        # ���ʵ���ϣ����һ���ӵ�close��ֵ
        series_last_price = get_last_price(C, stock_code)

        # ��series�У��õ����������
        today = series_last_price._name[:8]  # ��õ��������

        # ��series�У��õ����һ���ӵļ۸�
        last_price = series_last_price.item()

        # �ж��Ƿ���Ҫ���¼������ݣ�ֻ�л�������ݵ�������ںͽ��첻һ�µ�ʱ�򣬲���Ҫ���¼���
        df = load_data(C, stock_code, today)

        # �õ����һ���MA
        last_ma = df.iloc[-1].ma

        # ������İٷֱ�
        diff2last = (last_price - last_ma) / last_ma

        # ������
        A.broker.set_context(C)
        # last_price�������ĺ�Ȩ�۸�ע���Ǻ�Ȩ
        msg = A.strategy.handle_one_fund(stock_code, str2date(date), last_price, last_ma, diff2last)

        if msg:
            weixin('detail', f"[{POLICY_NAME}] ��������:\n{msg}")
            mail(f'[{POLICY_NAME}] ��������', f"{msg}")




