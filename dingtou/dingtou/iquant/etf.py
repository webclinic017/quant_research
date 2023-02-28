# encoding:gbk
import logging
import csv
from importlib import reload
import time
import os
import traceback

import dingtou
from dingtou.pyramid_v2.pyramid_v2_strategy import PyramidV2Strategy
from dingtou.pyramid_v2.position_calculator import PositionCalculator

from dingtou.utils.imessage import MessageSender
from dingtou.utils.utils import str2date, date2str, load_conf

import datetime

logger = logging.getLogger(__name__)

"""
# ʵ��ETF��Ͷ���ԣ�
    �������ŵĲ�������ǣ�7ֻ��Ʊ��[-0.4~0.8]������������ֵ��850�վ��ߣ���������Ϊ1:2 ==> 7%/�껯��2013~2023��

# �汾ά����
- 2023.2.15 �������ǰ���Ż��͵��ԣ�������plusplus���ͣ�ȷ����ǰ��Ȩ����ȷ��
- 2023.2.16 
    - ���ߺ��쳣�޸���PyramidV2Strategy���캯��������ƥ�䵼��
    - �޸�����ʾ��ֻ��ʾȱ���ʽ�1�Σ���is_new_bar
- 2023.2.18
    - �����˿��̡����̷���һ�²�λ���
- 2023.2.28 
    - ���봴ҵ�壬֮ǰ�زⲻ�������룬�����л��ᣬ����Ҳ�����ˣ�֮����review�����¼ӻ�17ֻ
    - �ع�����Ϣ���ͣ��ѷ�����Ϣ�ĳ鵽��MessageSender�У�����ͳһ����ͽ����ĸ���
    - ÿ�������500Ԫ

���лز�Ĳ�����
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

# �������еĲ�������Щ�������Ǿ����ز�����ŵģ����������20230215���£�
# stocks = ["159915.SZ","512690.SH", "512580.SH", "512660.SH", "159915.SZ", "159928.SZ", "510330.SH", "510500.SH"]
# ʵ�̺󣬸о������٣����⣬��������ĿƼ����뵼�嶼�ܺõ�λ��ȴû��ѡ�У����µ�����17ֻ
stocks = ["510330.SH", "510500.SH", "159915.SZ", "588090.SH", "512880.SH", "512200.SH", "512660.SH", "512010.SH",
          "512800.SH", "512690.SH", "510810.SH", "512980.SH", "512760.SH", "159928.SZ", "515000.SH", "516160.SH",
          "512580.SH"]


class Args():
    grid_height = 0.01
    grid_amount = 500
    quantile_positive = 0.8
    quantile_negative = 0.4
    ma = 850
    buy_factor = 1
    sell_factor = 2


args = Args()

# �������е�Ŀ¼
home_dir = "c:\\workspace\\iquant"
log_dir = f"{home_dir}\\logs"
conf_path = f"{home_dir}\\config.yml"
data_dir = f"{home_dir}\\data"
trans_log = f"{data_dir}\\transaction.csv"
last_grid_position = f"{data_dir}\\last_grid_position.json"

POLICY_NAME = 'ETF��Ͷ'
MAX_TRADE_NUM_PER_DAY = 3  # ÿ��ÿֻ��Ʊ���Ľ��״������������
MIN_CASH = 80000  # С������ʽ𣬾�Ҫ�����ˣ���ֹ�ʽ𲻹���Ĭ����300000�ȽϺ��ʣ�����20�����ѣ�Ȼ����ת֤��30��


conf = load_conf(conf_path)


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
        ����quickTrade��������Ϊ1ʱ������ʷbar��ִ��ʱ��ContextInfo.is_last_bar()ΪTrue����
        ֻҪ����ģ���е��õ��ʹ����µ����ס�
        quickTrade��������Ϊ2ʱ�����ж�bar״̬��ֻҪ����ģ���е��õ��ʹ����µ����ף���ʷbar��Ҳ�ܴ����µ��������ʹ�á�

        logger.debug("�˺�%s�������%s %.0f��",self.account,code,position)
        self.context.passorder(
         opType=23, # ��Ʊ���룬�򻦸�ͨ�����ͨ��Ʊ����
         orderType=1101, # 1101 ���ɡ����˺š���ͨ����/�ַ�ʽ�µ�, 1102�����ɡ����˺š���ͨ����Ԫ����ʽ�µ���ֻ֧�ֹ�Ʊ��
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
        # ���չ��������������������µ�����������ο��ã���ʹ��
        # passorder(23,1101, self.account, code, 3, 0, positoin, POLICY_NAME,1,order_id,self.context)
        # ����Ǯ�������µ���������ΪA��������1��(100��)�����ƣ����ԣ��������Զ�ȡ����100�ɵ�������
        # passorder(23,1102, self.account, code, 3, 0, amount, POLICY_NAME,1,order_id,self.context)

        # ����Ƿ�غͷ�ֹbug����Ҫ����ֹһ�첻ͣ����ÿ�β��µ��ճɽ�����������3�ξͲ��ùҵ���
        if self.check_max_trade(code):
            msg = "����ʧ�ܣ������������������״���[%d��]���˺�%s��%s�հ�����2�ۣ��������%s: %.0fԪ" % (
                MAX_TRADE_NUM_PER_DAY, self.account, date2str(date), code, amount)
            logger.warning(msg)
            A.messager.send(f'[{POLICY_NAME}] ������ʧ��', f"{msg}", A.messager.ERROR)
            return False

        my_cash = self.get_available_cash()
        if my_cash < amount:
            msg = "����ʧ�ܣ�������С�ڿ��ý��[%.2f]���˺�%s��%s�հ�����2�ۣ��������%s: %.0fԪ" % (
                my_cash, self.account, date2str(date), code, amount)
            logger.warning(msg)
            A.messager.send(f'[{POLICY_NAME}] ������ʧ��', f"{msg}", A.messager.ERROR)
            return False

        old_postions = get_trade_detail_data(self.account, 'stock', 'position')
        order_time = time.strftime('%Y%m%d%H%M%S', time.localtime(time.time()))
        order_id = f"{order_time}_{code}_{POLICY_NAME}"

        # 23:��Ʊ;1102���������;3:��2����1:������Ч
        passorder(23, 1102, self.account, code, 3, 0, amount, POLICY_NAME, 1, order_id, self.context)

        msg = "�˺�%s��%s�հ�����2�ۣ��������%s: %.0fԪ" % (self.account, date2str(date), code, amount)
        logger.info(msg)

        A.messager.send(f'[{POLICY_NAME}] ������', f"{msg}", A.messager.SIGNAL)

        postions = get_trade_detail_data(self.account, 'stock', 'position')

        time.sleep(1)  # ��1��
        for p in old_postions:
            if p.m_strInstrumentID != code: continue
            # ����ǰ����ӡһ�¾ɵĳֲ�
            logger.info("����ǰ���ֲ֣�%s : %.0f��", p.m_strInstrumentID, p.m_nVolume)

        for p in postions:
            # ����󣬴�ӡһ���µĳֲ�
            if p.m_strInstrumentID != code: continue
            logger.info("����󣬳ֲ֣�%s : %.0f��", p.m_strInstrumentID, p.m_nVolume)
        return True

    def sell(self, code, date, amount=None, position=None):

        """
        �����߼��ǲ�λ�Ķ���

        passorder(
         opType = 24, # 24����Ʊ�������򻦸�ͨ�����ͨ��Ʊ����
         orderType = 1102, # ���ɡ����˺š���ͨ����Ԫ����ʽ�µ���ֻ֧�ֹ�Ʊ��
         accountid = self.account,
         orderCode = code,
         prType = 7, # �µ�ѡ�����ͣ�6����1�ۣ�7����2��
         price = 0,
         volume = amount,
         ContextInfo= self.context )
        """

        # ����Ƿ�غͷ�ֹbug����Ҫ����ֹһ�첻ͣ����ÿ�β��µ��ճɽ�����������3�ξͲ��ùҵ���
        if self.check_max_trade(code):
            msg = "������ʧ�ܣ������������������״���[%d��]���˺�%s��%s�հ�����2�ۣ��������%s: %.0fԪ" % (
                MAX_TRADE_NUM_PER_DAY, self.account, date2str(date), code, amount)
            logger.error(msg)
            A.messager.send(f'[{POLICY_NAME}] ��������ʧ��', f"{msg}", A.messager.ERROR)
            return False

        old_postions = postions = get_trade_detail_data(self.account, 'stock', 'position')
        available_amount = None
        for p in postions:
            # logger.debug("������%s ��%.0f", p.m_strInstrumentID, p.m_nVolume)
            # code��510500.SH������m_strInstrumentID��510500������ֻȡǰ6λ
            if p.m_strInstrumentID == code[0:6] and p.m_dMarketValue < amount:
                available_amount = p.m_dMarketValue
            if p.m_strInstrumentID == code[0:6] and p.m_dMarketValue >= amount:
                available_amount = amount

        if available_amount is None:
            logger.warning("�˺�%s��%s����������%s %.0fԪʧ�ܣ�û�гֲ�", self.account, date2str(date), code, amount)
            return False

        order_time = time.strftime('%Y%m%d%H%M%S', time.localtime(time.time()))
        order_id = f"{order_time}_{code}_{POLICY_NAME}"

        # 1102��ʹ�ý�ʽ�������������ǰ��ս��������
        # ������2�۽������룬ûѡ��1�����������quickTrade=1�����������ö�����Ч�������õȵ�bar�����һ��tick
        passorder(24, 1102, self.account, code, 7, 0, available_amount, POLICY_NAME, 1, order_id, self.context)

        msg = "�˺�%s��%s�հ�����2�ۣ���������%s %.0fԪ��������[%s]" % (
            self.account, date2str(date), code, available_amount, order_id)
        logger.info(msg)
        A.messager.send(f'[{POLICY_NAME}] ������', f"{msg}", A.messager.SIGNAL)

        postions = get_trade_detail_data(self.account, 'stock', 'position')

        time.sleep(1)  # ��1��
        for p in old_postions:
            if p.m_strInstrumentID != code: continue
            # ����ǰ����ӡһ�¾ɵĳֲ�
            logger.info("����ǰ���ֲ֣�%s : %.0f��", p.m_strInstrumentID, p.m_nVolume)

        for p in postions:
            # ����󣬴�ӡһ���µĳֲ�
            if p.m_strInstrumentID != code: continue
            logger.info("����󣬳ֲ֣�%s : %.0f��", p.m_strInstrumentID, p.m_nVolume)
        return True


# �����յ����ʵ�� ��������ί��״̬
# ContextInfo����������ÿ��handlebar����ǰ���ᱻ���,
# �������handlebar�ķֱʲ���k�����ֱ� ContextInfo�ᱻ���˵����������
# ����ContextInfo����������¼���ٽ��׵��ź�
class a():
    pass


A = a()


def init(ContextInfo):
    logger.info('���Կ�ʼ��ʼ��...')

    init_logger(logging.INFO)

    # ��֪Ϊ�Σ�ʵ���޷�reload��
    if not _is_realtime(ContextInfo):
        reload(dingtou)
        reload(dingtou.pyramid_v2.pyramid_v2_strategy)
        reload(dingtou.utils.utils)
        logger.info("���¼���python��")

    if not os.path.exists(data_dir):
        os.makedirs(data_dir)

    A.acct = conf['account']  # �˺�Ϊģ�ͽ��׽���ѡ���˺�
    A.acct_type = 'stock'  # �˺�����Ϊģ�ͽ��׽���ѡ���˺�
    A.stock_list = stocks
    A.data = {}
    A.messager = MessageSender(conf)  # ����Ϣ�õ�

    ContextInfo.trade_code_list = stocks
    ContextInfo.set_universe(ContextInfo.trade_code_list)
    ContextInfo.set_account(A.acct)  # ֮ǰδ���ã�����deal_callbackδ�ص�����ѯ�˿ͷ����뵽
    ContextInfo.buy = True  # ����Ҫ���ã����򣬾Ͳ��ᴥ���������Ĭ�϶���False
    ContextInfo.sell = True

    logger.info("���ù�Ʊ�أ�%r", ContextInfo.trade_code_list)
    policy = PositionCalculator(args.grid_amount)

    A.broker = Broker(A.acct)
    A.strategy = PyramidV2Strategy(
        A.broker,
        args,
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
        dividend_type='front')  # ����ǰ��Ȩ����Ȩ���ش����⣬�ᵼ��ƫ����ߺܴ󣬵��´�����,20230215

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

    A.messager.send(f'[{POLICY_NAME}] ���׳ɹ�', f"{headers}\n{data}", A.messager.SIGNAL)

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
    # ��������������ݣ����ǵ�1��bar�����̼ۣ���������ݣ�������850���ߣ����ϸ����Ҫע�⣬������������̼�
    start_date = str(C.get_open_date(stock_code))  # �õ���������
    df = C.get_market_data(
        fields=['close'],
        stock_code=[stock_code],
        start_time=start_date,  # ����Ҫ�ƶ�����ʱ�䣬���򣬸��ҷ���һ�ѵ������������2019�����У����2400������2013������ȫ�Ǽٵ�
        count=2400,  # Ϊ��Ҫ�ҳ��ܳ�����ʷ�µ�80%��20%��λ������Ҫ����ʮ��ģ���ʵֻ��8������ݣ���Ϊ��2����Ҫ���ƶ�ƽ��������na
        period='1d',  # ������õ������Ϣ
        dividend_type='front')  # ������ǰ��Ȩ����Ҫ��Ϊ�˻�����µļ۸�
    df.to_csv(f"{data_dir}\\{stock_code}.csv")
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
        logger.exception("handlerbar�쳣")
        A.messager.send(f'[{POLICY_NAME}] �����쳣', f"{msg}", A.messager.ERROR)


def get_account_info():
    result = ''
    account_info = get_trade_detail_data(A.acct, 'stock', 'account')
    for i in account_info:
        info = f'���ʲ�:{i.m_dBalance},���ý��:{i.m_dAvailable},����ֵ:{i.m_dInstrumentValue},��ӯ��:{round(i.m_dPositionProfit, 2)}'
        result += f'{info}\n'
    return result


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

    # ���̺������ǰ������ʽ��㣬�����ѣ�is_new_bar������һ��
    # ���⣬������9:30�֣���Ϊ���������£�handlebar �Żᱻ����������ǰ����������handlebar��
    if _is_realtime(C) and C.is_new_bar() and (now_time[:4] == '0930' or now_time[:4] == "1458"):
        account = get_trade_detail_data(A.acct, A.acct_type, 'account')
        account = account[0]
        available_cash = int(account.m_dAvailable)

        # ÿ�쿪ʼ�ͽ�����������һ���ҵ��ʲ���Ϣ
        account_information = get_account_info()
        logger.info("[%s] �����˻���Ϣ��%s", now_time, account_information)
        A.messager.send(f'[{POLICY_NAME}] �˻���Ϣ����', f"{account_information}", A.messager.SIGNAL)

        # logger.debug("��������: %s, �˺ţ�%s,�����ʽ�%.2f",date, A.acct, available_cash)
        if available_cash < MIN_CASH:
            msg = "�ֽ��㣺��ǰ�ֽ� %.0f Ԫ < ���ٵ�Ҫ�� %.0f Ԫ���벹���ֽ�" % (available_cash, MIN_CASH)
            logger.warning(msg)
            A.messager.send(f'[{POLICY_NAME}] �벹���ֽ�', f"{msg}", A.messager.ERROR)

    if _is_realtime(C) and (now_time < '093000' or now_time > "150000"):
        logger.warning("���ڽ���ʱ�䣺%s", now_time)
        return

    """
    logger.debug("K������%d,bar�ĵ�һ��tick:%r,K�ߺ�:%d,���һ��bar:%r",
        C.time_tick_size,
        C.is_new_bar(), # ĳ�� K �ߵĵ�һ�� tick ���ݵ���ʱ���ж��� K ��Ϊ�µ� K ��
        C.barpos,
        C.is_last_bar())
    """

    # ����������Ҫ�����򣬾ͻ�3��һ��tick�ͻᴥ������һ�Σ����¸��ָ��������⣬��Ƶ������
    # ֮ǰ��һֱû�ҵ������������Ϊû���أ�����
    # ����������Ҿ�ֻ�������õĽ��׻ص�������һ��tick���������������õ�1���ӣ�����ֻ��������ӵĵ�20��tick�Ŵ�������
    # �Żᴥ�������򣬾�����ķ�����
    if not C.is_last_bar():
        return

    # ע���ڻز�ģʽ�У����׺������������˺Ž��н��ף�����ʷ K ���ϼ�¼�����㣬���Լ�����Ծ�ֵ/
    # �ز�ָ�ꣻʵ�����е��ò��������õ��ʽ��˺Ž��н��ף�����ʵ��ί�У�ģ������ģʽ�½��׺�����
    # Ч�����У�can_cancel_order, cancel��do_order���׺����ڻز�ģʽ����ʵ�����壬������ʹ�á�
    account = get_trade_detail_data(A.acct, A.acct_type, 'account')
    if len(account) == 0:
        logger.warning(f'�˺�{A.acct} δ��¼ ����')
        return

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
            A.messager.send(f'[{POLICY_NAME}] ���Դ�������', f"{msg}", A.messager.SIGNAL)
