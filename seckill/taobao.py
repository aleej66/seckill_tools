import json
import logging
from time import sleep
from datetime import datetime

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from utils.utils import notify_user
from utils.utils import build_chrome_options

# 抢购失败最大次数
max_retry_count = 30
# 配置logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(filename)s:%(lineno)d] - %(message)s')
logger = logging.getLogger(__name__)

# 自动抢票类（TBao）
class TaoBao:

    def __init__(self, chrome_path="./chromedriver.exe", seckill_time_str=None, password=None):
        # 驱动路径
        self.chrome_path = chrome_path
        # 抢购时间
        self.seckill_time = datetime.strptime(seckill_time_str, '%Y-%m-%d %H:%M:%S')
        # 支付密码
        self.password = password
        # chrome驱动
        self.driver = None

    # 获取chrome驱动
    def start_driver(self):
        try:
            driver = self.find_chromedriver()
        except WebDriverException:
            logger.error("Unable to find chromedriver, Please check the drive path.")
        else:
            return driver

    # 寻找chrome驱动（首先去python安装目录下找，其次再去传入的路径找）
    def find_chromedriver(self):
        try:
            driver = webdriver.Chrome()
        except WebDriverException:
            try:
                driver = webdriver.Chrome(executable_path=self.chrome_path, chrome_options=build_chrome_options())
            except WebDriverException:
                raise Exception("Unable to find chromedriver, Please check the drive path.")
        return driver

    # 登录TBao
    def login(self, login_url="https://www.taobao.com", login_time_out=10):
        if login_url:
            self.driver = self.start_driver()
        else:
            raise Exception("Please input the login url.")
        while True:
            # 打开首页
            self.driver.get(login_url)
            try:
                # 尝试获取点击登录超链接
                a_lists = self.driver.find_elements(By.XPATH, '//div[@class="site-nav-sign"]/a')
                # 获取到了，说明还未登录，进行登录
                if len(a_lists) > 0:
                    logger.info("没登录，开始点击登录按钮...")
                    # 亲，请登录
                    login_button = a_lists[0]
                    login_button.click()
                    logger.info("请在{}s内扫码登陆!!".format(login_time_out))
                    # 睡眠login_time_out(s)
                    sleep(login_time_out)
                    # 尝试获取登录成功页面的元素，找到了表示已经登录成功。
                    if self.driver.find_element(By.XPATH, '//*[@id="J_SiteNavMytaobao"]/div[1]/a/span'):
                        logger.info("登陆成功")
                        # 进入购物车
                        self.driver.get("https://cart.taobao.com/cart.htm")
                        # 结束循环
                        break
                    else:
                        logger.info("登陆失败, 刷新重试, 请尽快登陆!!!")
                        continue
            except Exception as e:
                logger.error(str(e))
                continue

    # 等待抢购
    def keep_wait(self):
        logger.info("等待到点抢购...")
        while True:
            # 获取当前时间
            current_time = datetime.now()
            # 如果距离抢购时间大于3分钟，则每分钟刷新一次界面，防止登录超时。
            if (self.seckill_time - current_time).seconds > 180:
                # 进入购物车
                self.driver.get("https://cart.taobao.com/cart.htm")
                logger.info("每分钟刷新一次界面，防止登录超时...")
                sleep(60)
            else:
                # 调用函数，将浏览器cookie写入文件备用。
                self.get_cookie()
                logger.info("抢购时间点将近，停止自动刷新，准备进入抢购阶段...")
                # 抢购时间将近，结束等待抢购
                break

    # 抢购的入口函数
    def sec_kill(self, login_time_out=15, max_retry_count=5):
        logger.info("此次抢购时间：{}".format(datetime.strftime(self.seckill_time, "%Y-%m-%d %H:%M:%S")))
        # 调用登录函数
        self.login(login_time_out=login_time_out)
        # 调用等待抢购函数
        self.keep_wait()
        # 获取全选框
        select_all = self.driver.find_element(By.ID, "J_SelectAll1")
        if select_all:
            logger.info("当前未选状态，自动选择全部商品")
            # 点击全选
            select_all.click()
        logger.info("已经选中全部商品！！！")

        # 记录提交状态
        submit_success = False
        # 重试抢购次数
        retry_count = 0

        while True:
            # 获取当前时间
            now = datetime.now()
            if now >= self.seckill_time:
                logger.info(f"开始抢购, 尝试次数： {retry_count + 1}")
            else:
                # 睡眠一段时间,防止cpu一直工作
                sleep(0.5)  # 增加睡眠时间
                continue

            try:
                # 封装等待元素可点击的逻辑
                def wait_for_clickable(selector, timeout=5):
                    return WebDriverWait(self.driver, timeout, poll_frequency=0.1).until(
                        EC.element_to_be_clickable(selector)
                    )

                # 等待结算按钮可以被点击
                button = wait_for_clickable((By.CSS_SELECTOR, '#J_SmallSubmit'))
                # 点击结算
                button.click()
                logger.info("已经点击结算按钮...")
                # 等待跳转到提交订单按钮可以被点击
                submit = wait_for_clickable((By.CSS_SELECTOR, '#submitOrderPC_1 > div > a.go-btn'))
                # 点击提交订单
                submit.click()
                logger.info("已经点击提交订单按钮...")
                # 记录提交状态
                submit_success = True
                break
            except Exception as e:  # 捕获特定异常
                logger.info(e)
                logger.info("临时写的脚本, 可能出了点问题!!!")
                retry_count += 1
                if retry_count > max_retry_count:
                    logger.info("重试抢购次数达到上限，放弃重试...")
                    break

        # 提交成功,准备支付
        if submit_success:
            if self.password:
                self.pay()

    def pay(self):
        try:
            # 等待密码框加载完毕
            element = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.CLASS_NAME, 'sixDigitPassword')))
            # 输入密码
            element.send_keys(self.password)
            logger.info("密码输入完成")
            # 等待确认付款按钮加载完成,并付款
            WebDriverWait(self.driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, '#J_authSubmit'))).click()
            logger.info("付款成功")
            notify_user()
        except Exception as e:
            logger.info(e)
            notify_user(text="商品抢购失败")
        finally:
            logger.info("20s后关闭浏览器...")
            sleep(20)
            self.driver.quit()

    def get_cookie(self):
        """
        将浏览器cookie存入文件
        :return:
        """
        # 获取浏览器cookies（dict类型）
        cookies = self.driver.get_cookies()
        # 将cookie转换为json字符串，并写入文件
        cookie_json = json.dumps(cookies)
        with open('./tb_cookies.txt', 'w', encoding='utf-8') as f:
            f.write(cookie_json)
