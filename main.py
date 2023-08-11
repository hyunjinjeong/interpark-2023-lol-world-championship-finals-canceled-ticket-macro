# 파이썬 내장 라이브러리
import re
from time import sleep
from winsound import Beep, MessageBeep
from datetime import datetime, timezone, timedelta
from pathlib import Path
from os import remove

# 따로 설치해야 하는 라이브러리
import cv2 as cv
import numpy
from pytesseract import image_to_string
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    WebDriverException,
)
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# 목표 URL
URL = "https://tickets.interpark.com/special/sports/promotion?seq=22"
# 목표 좌석 Tier 범위. 각각 1부터 8까지 가능. 나머지 값은 무시 (전체 범위). TARGET_MIN_TIER <= TARGET_MAX_TIER여야 함.
TARGET_MIN_TIER = 1
TARGET_MAX_TIER = 8
# 로그인에 사용되는 아이디와 비밀번호
USER_ID = "YOUR_ID"
USER_PW = "YOUR_PW"
# 새로고침 주기.
REFRESH_INTERVAL_IN_SECONDS = 0.5
# 브라우저 로딩에 기다려줄 최대 시간
WAIT_LIMIT_IN_SECONDS = 5
# 드라이버 리로드까지의 루프 횟수. 루프문을 계속 돌리면 메모리 때문에 크롬이 에러가 남. 정해진 횟수마다 드라이버 리로드 시켜준다.
LOOP_LIMIT = 2400

TMP_CAPTCHA_IMAGE_PATH = Path(__file__).parent.absolute() / "_captcha.png"
CHROME_DRIVER_PATH = Path(__file__).parent.absolute() / "static" / "chromedriver.exe"


class LoopEndException(Exception):
    pass


class BuyFailException(Exception):
    pass


def run():
    should_retry = False
    try:
        driver = load_driver()

        login_to_site(driver)
        captcha(driver)
        row_num = find_canceled_ticket(driver)

        ticket_name = get_ticket_name_to_buy_and_click(driver, row_num)
        try_to_buy(driver, ticket_name)
        # 20분 정도 대기 후 종료
        sleep(60 * 20)
    except (LoopEndException, BuyFailException, WebDriverException):
        should_retry = True
    finally:
        driver.quit()
        if should_retry:
            run()


def load_driver():
    service = Service(executable_path=str(CHROME_DRIVER_PATH))

    options = webdriver.ChromeOptions()
    options.add_argument("force-device-scale-factor=1")
    options.add_argument("log-level=3")
    options.add_experimental_option("excludeSwitches", ["enable-logging"])

    driver = webdriver.Chrome(service=service, options=options)
    driver.implicitly_wait(WAIT_LIMIT_IN_SECONDS)
    print_msg("드라이버 시작")
    MessageBeep()
    return driver


def login_to_site(driver: WebDriver):
    def close_popup():
        popup = driver.find_element(
            by=By.XPATH, value="/html/body/div[1]/div/div[2]/div/div[3]/button"
        )
        WebDriverWait(driver, WAIT_LIMIT_IN_SECONDS).until(
            EC.element_to_be_clickable(popup)
        )
        popup.click()
        WebDriverWait(driver, WAIT_LIMIT_IN_SECONDS).until(
            EC.invisibility_of_element(popup)
        )

    def click_final_button():
        final_button = driver.find_element(
            by=By.XPATH,
            value="/html/body/div[1]/div/div[2]/div/div[2]/div[2]/ul/li[7]/div/div[3]/button",
        )
        WebDriverWait(driver, WAIT_LIMIT_IN_SECONDS).until(
            EC.element_to_be_clickable(final_button)
        )
        final_button.send_keys(Keys.ENTER)

    def login():
        driver.get("https://ticket.interpark.com/Gate/TPLogin.asp")
        driver.switch_to.frame(driver.find_element(by=By.TAG_NAME, value="iframe"))
        WebDriverWait(driver, WAIT_LIMIT_IN_SECONDS).until(
            EC.presence_of_element_located((By.ID, "btn_login"))
        )

        driver.find_element(by=By.ID, value="userId").send_keys(USER_ID)
        driver.find_element(by=By.ID, value="userPwd").send_keys(USER_PW)
        driver.find_element(by=By.ID, value="btn_login").click()

    login()
    driver.get(URL)
    # 모바일 인터페이스가 더 편함. width에 따른 반응형 디자인임.
    driver.set_window_size(760, 1000)
    close_popup()
    click_final_button()


# ref: https://github.com/clyde0813/Interpark-Ticketing/blob/main/interpark.py
def captcha(driver: WebDriver):
    def save_captcha_image():
        captcha_image_element = driver.find_element(by=By.ID, value="imgCaptcha")
        captcha_image = captcha_image_element.screenshot_as_png
        with open(TMP_CAPTCHA_IMAGE_PATH, "wb") as f:
            f.write(captcha_image)

    def extract_text_from_captcha():
        image = cv.imread(str(TMP_CAPTCHA_IMAGE_PATH))
        image = cv.cvtColor(image, cv.COLOR_BGR2GRAY)
        image = cv.adaptiveThreshold(
            image, 255, cv.ADAPTIVE_THRESH_GAUSSIAN_C, cv.THRESH_BINARY, 91, 1
        )
        kernel = cv.getStructuringElement(cv.MORPH_RECT, (3, 3))
        image = cv.morphologyEx(image, cv.MORPH_OPEN, kernel, iterations=1)

        cnts = cv.findContours(image, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
        cnts = cnts[0] if len(cnts) == 2 else cnts[1]
        for c in cnts:
            area = cv.contourArea(c)
            if area < 50:
                cv.drawContours(image, [c], -1, (0, 0, 0), -1)
        kernel2 = numpy.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
        image = cv.filter2D(image, -1, kernel2)
        result = 255 - image

        captcha_text = image_to_string(result)
        captcha_text = re.sub("[^A-Z]", "", captcha_text) or "A"  # 빈 텍스트인 경우 아무거나 넣어줌
        return captcha_text

    def submit_captcha(captcha_text: str):
        captcha_input = driver.find_element(by=By.ID, value="txtCaptcha")
        captcha_input.send_keys(captcha_text)

        captcha_submit_button = driver.find_element(
            by=By.XPATH, value="/html/body/div/div/div/div/div[3]"
        )
        captcha_submit_button.click()

    def retry_if_wrong():
        try:
            captcha_wrong_alert = driver.find_element(
                by=By.XPATH, value="/html/body/div/div/div/div/div[2]/div"
            )

            if captcha_wrong_alert.get_attribute("class") == "alert":
                driver.execute_script("reloadCapcha();")
                captcha(driver)
        except NoSuchElementException:  # 성공한 경우 없어짐
            pass

    WebDriverWait(driver, WAIT_LIMIT_IN_SECONDS).until(
        EC.presence_of_element_located((By.ID, "imgCaptcha"))
    )

    save_captcha_image()
    captcha_text = extract_text_from_captcha()
    submit_captcha(captcha_text)
    retry_if_wrong()

    if TMP_CAPTCHA_IMAGE_PATH.exists():
        remove(TMP_CAPTCHA_IMAGE_PATH)


def find_canceled_ticket(driver: WebDriver):
    def get_start_and_end_range():
        print_msg(f"최소 티어: {TARGET_MIN_TIER}, 최대 티어: {TARGET_MAX_TIER}")

        start, end = 0, 11
        if TARGET_MIN_TIER > TARGET_MAX_TIER:
            print_msg(
                f"전체 범위로 초기화. 최소 티어({TARGET_MIN_TIER})가 최대 티어({TARGET_MAX_TIER})보다 높음."
            )
            return start, end

        if TARGET_MIN_TIER in (1, 2, 3, 4):
            start = TARGET_MIN_TIER - 1
        elif TARGET_MIN_TIER in (5, 6, 7):
            start = TARGET_MIN_TIER
        elif TARGET_MIN_TIER == 8:
            start = TARGET_MIN_TIER + 1  # 9

        if TARGET_MAX_TIER in (1, 2, 3):
            end = TARGET_MAX_TIER
        elif TARGET_MAX_TIER in (4, 5, 6):
            end = TARGET_MAX_TIER + 1
        elif TARGET_MAX_TIER == 7:
            end = TARGET_MAX_TIER + 2  # 9
        elif TARGET_MAX_TIER == 8:
            end = TARGET_MAX_TIER + 3  # 11

        return start, end

    def get_row_num_of_canceled_ticket(start: int, end: int):
        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")

        remained_counts = [
            int(li.get("data-remaincnt"))
            for li in soup.select("div.seatListBlock > ul > li")
        ]

        for index, remained_count in enumerate(remained_counts[start:end]):
            if remained_count != 0:
                return index + 1
        return -1

    start, end = get_start_and_end_range()
    i = 0
    while i < LOOP_LIMIT:
        WebDriverWait(driver, WAIT_LIMIT_IN_SECONDS, poll_frequency=0.1).until(
            EC.presence_of_element_located((By.ID, "seatClass1"))
        )

        row_num = get_row_num_of_canceled_ticket(start, end)
        if row_num != -1:
            break

        sleep(REFRESH_INTERVAL_IN_SECONDS)
        i += 1

        driver.refresh()

    if row_num == -1:
        raise LoopEndException()

    return row_num


def get_ticket_name_to_buy_and_click(driver: WebDriver, row_num: int):
    tier = driver.find_element(
        by=By.XPATH, value=f"/html/body/div/div[2]/div[2]/ul/li[{row_num}]"
    )
    WebDriverWait(driver, WAIT_LIMIT_IN_SECONDS, poll_frequency=0.1).until(
        EC.element_to_be_clickable(tier)
    )
    tier_name = tier.get_attribute("data-seatgradename")

    tier.click()

    seat_auto_assign_button = driver.find_element(
        by=By.XPATH, value="/html/body/div/div[3]/a[1]"
    )
    WebDriverWait(driver, WAIT_LIMIT_IN_SECONDS, poll_frequency=0.1).until(
        EC.element_to_be_clickable(seat_auto_assign_button)
    )
    seat_auto_assign_button.click()

    return tier_name


def try_to_buy(driver: WebDriver, ticket_name: str):
    def up_ticket_count():
        WebDriverWait(driver, WAIT_LIMIT_IN_SECONDS, poll_frequency=0.1).until(
            EC.presence_of_element_located((By.ID, "delymethod_22012"))
        )

        up_ticket_count = driver.find_element(
            by=By.XPATH, value="/html/body/div[3]/div[1]/ul/li/div[1]/div/a[1]"
        )
        up_ticket_count.click()

    def click_delivery_method_button():
        # ::before로 구현된 button 클릭
        driver.execute_script(
            """
            const radioButtons = document.querySelectorAll('.selection li[dely_type="deliveryMethod"]');
            radioButtons[1].click();
            """
        )

    def click_buy_button():
        buy_button = driver.find_element(by=By.ID, value="step_noti_txt")
        WebDriverWait(driver, WAIT_LIMIT_IN_SECONDS, poll_frequency=0.1).until(
            EC.text_to_be_present_in_element_attribute(
                (By.ID, "step_noti_txt"), "class", "buy"
            )
        )
        buy_button.click()

    def handle_result():
        # alert가 뜨면 실패한 것
        try:
            WebDriverWait(driver, WAIT_LIMIT_IN_SECONDS, poll_frequency=0.1).until(
                EC.alert_is_present()
            )
            alert = driver.switch_to.alert
            alert.accept()
            print_msg(f"{ticket_name} 좌석 배정 실패")
            Beep(frequency=500, duration=1000)
        except TimeoutException:
            print_msg(f"{ticket_name} 좌석 배정 성공. 7분 안에 결제 필요")
            Beep(frequency=1000, duration=3000)
        else:
            raise BuyFailException()

    up_ticket_count()
    click_delivery_method_button()
    click_buy_button()
    handle_result()


def print_msg(msg: str):
    def get_current_date_time_kst():
        now = datetime.now(timezone(timedelta(hours=9)))
        return f"[{now.isoformat().split('.')[0]}]"

    print(get_current_date_time_kst(), msg)


if __name__ == "__main__":
    run()
