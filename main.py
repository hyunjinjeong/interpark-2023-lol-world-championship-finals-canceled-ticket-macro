# 파이썬 내장 라이브러리
import re
from time import sleep
from winsound import Beep
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
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# 목표 URL
URL = "https://tickets.interpark.com/special/sports/promotion?seq=22"
# Tier 어디까지 확인할 것인지... -1이면 전부
TARGET_MAX_TIER = -1
# 로그인에 사용되는 아이디와 비밀번호
USER_ID = "YOUR_ID"
USER_PW = "YOUR_PW"
# 새로고침 주기.
REFRESH_INTERVAL_IN_SECONDS = 0.5
# 브라우저 로딩에 기다려줄 최대 시간
WAIT_LIMIT_IN_SECONDS = 5
# 드라이버 리로드까지의 루프 횟수.
LOOP_LIMIT = 1200

TMP_CAPTCHA_IMAGE_PATH = Path(__file__).parent.absolute() / "_captcha.png"
CHROME_DRIVER_PATH = Path(__file__).parent.absolute() / "static" / "chromedriver.exe"


class _LoopEndException(Exception):
    pass


class _BuyFailException(Exception):
    pass


def run(driver: WebDriver = None):
    try:
        if driver is None:
            driver = _load_driver()

        _login(driver)
        _captcha(driver)
        row_num = _find_canceled_ticket(driver)

        ticket_name = _get_ticket_name_to_buy_and_click(driver, row_num)
        _buy(driver, ticket_name)
    except _LoopEndException:
        _print_msg(f"루프 {LOOP_LIMIT}회 도달. 드라이버 재시작.")
        _exit_driver(driver)
        run()
    except _BuyFailException:
        _print_msg("구매 실패, 드라이버 재시작")
        _exit_driver(driver)
        run()
    except Exception as err:
        _print_msg(f"{str(err)}, 드라이버 재시작")
        _exit_driver(driver)
        run()
    else:
        _exit_driver(driver)


def _load_driver():
    service = Service(executable_path=str(CHROME_DRIVER_PATH))

    options = webdriver.ChromeOptions()
    # 모바일 인터페이스가 더 편함. width에 따른 반응형.
    options.add_argument("window-size=760,900")
    options.add_argument("force-device-scale-factor=1")

    driver = webdriver.Chrome(service=service, options=options)
    driver.implicitly_wait(WAIT_LIMIT_IN_SECONDS)

    _print_msg("드라이버 시작")
    return driver


def _exit_driver(driver: WebDriver):
    if driver is None:
        return

    _print_msg("드라이버 종료")
    driver.quit()


def _login(driver: WebDriver):
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
        WebDriverWait(driver, WAIT_LIMIT_IN_SECONDS).until(
            EC.url_contains("accounts.interpark.com")
        )
        driver.find_element(by=By.ID, value="userId").send_keys(USER_ID)
        driver.find_element(by=By.ID, value="userPwd").send_keys(USER_PW)
        driver.find_element(by=By.ID, value="btn_login").click()

    driver.get(URL)

    close_popup()
    click_final_button()
    login()
    close_popup()
    click_final_button()


# ref: https://github.com/clyde0813/Interpark-Ticketing/blob/main/interpark.py
def _captcha(driver: WebDriver):
    def save_captcha_image():
        captcha_image_element = driver.find_element(by=By.ID, value="imgCaptcha")
        captcha_image = captcha_image_element.screenshot_as_png
        with open(TMP_CAPTCHA_IMAGE_PATH, "wb") as f:
            f.write(captcha_image)

    def extract_string_from_captcha():
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

    def retry_if_wrong(captcha_text: str):
        try:
            captcha_wrong_alert = driver.find_element(
                by=By.XPATH, value="/html/body/div/div/div/div/div[2]/div"
            )

            if captcha_wrong_alert.get_attribute("class") == "alert":
                _print_msg(f"캡챠 실패: {captcha_text}")
                driver.execute_script("reloadCapcha();")
                _captcha(driver)
        except NoSuchElementException:  # 성공한 경우 없어짐
            _print_msg(f"캡챠 성공: {captcha_text}")

    WebDriverWait(driver, WAIT_LIMIT_IN_SECONDS).until(
        EC.presence_of_element_located((By.ID, "imgCaptcha"))
    )

    save_captcha_image()
    captcha_text = extract_string_from_captcha()
    submit_captcha(captcha_text)
    retry_if_wrong(captcha_text)

    if TMP_CAPTCHA_IMAGE_PATH.exists():
        remove(TMP_CAPTCHA_IMAGE_PATH)


def _find_canceled_ticket(driver: WebDriver):
    def get_row_num_of_canceled_ticket():
        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")

        remained_counts = [
            int(li.get("data-remaincnt"))
            for li in soup.select("div.seatListBlock > ul > li")
        ][:TARGET_MAX_TIER]

        for index, remained_count in enumerate(remained_counts):
            if remained_count != 0:
                return index + 1
        return -1

    i = 0
    # 루프문을 계속 돌리면 메모리 때문에 크롬이 에러가 남. 정해진 횟수마다 드라이버 리로드 시켜준다.
    while i < LOOP_LIMIT:
        WebDriverWait(driver, WAIT_LIMIT_IN_SECONDS).until(
            EC.presence_of_element_located((By.ID, "seatClass1"))
        )

        row_num = get_row_num_of_canceled_ticket()
        if row_num != -1:
            break

        sleep(REFRESH_INTERVAL_IN_SECONDS)
        i += 1

        driver.refresh()

    if row_num == -1:
        raise _LoopEndException()

    return row_num


def _get_ticket_name_to_buy_and_click(driver: WebDriver, row_num: int):
    tier = driver.find_element(
        by=By.XPATH, value=f"/html/body/div/div[2]/div[2]/ul/li[{row_num}]"
    )
    tier_name = tier.get_attribute("data-seatgradename")

    tier.click()

    seat_auto_assign_button = driver.find_element(
        by=By.XPATH, value="/html/body/div/div[3]/a[1]"
    )
    WebDriverWait(driver, WAIT_LIMIT_IN_SECONDS).until(
        EC.element_to_be_clickable(seat_auto_assign_button)
    )
    seat_auto_assign_button.click()

    return tier_name


def _buy(driver: WebDriver, ticket_name: str):
    def up_ticket_count():
        WebDriverWait(driver, WAIT_LIMIT_IN_SECONDS).until(
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
        WebDriverWait(driver, WAIT_LIMIT_IN_SECONDS).until(
            EC.text_to_be_present_in_element_attribute(
                (By.ID, "step_noti_txt"), "class", "buy"
            )
        )
        buy_button.click()

    def handle_result():
        # alert가 뜨면 실패한 것
        try:
            WebDriverWait(driver, WAIT_LIMIT_IN_SECONDS).until(EC.alert_is_present())
            alert = driver.switch_to.alert
            alert.accept()
            _print_msg(f"{ticket_name} 구매 실패")
            Beep(frequency=500, duration=1000)
        except TimeoutException:
            _print_msg(f"{ticket_name} 구매 성공")
            Beep(frequency=1000, duration=1000)
        else:
            raise _BuyFailException()

    up_ticket_count()
    click_delivery_method_button()
    click_buy_button()
    handle_result()


def _print_msg(msg):
    def get_current_time():
        now = datetime.now(timezone(timedelta(hours=9)))
        return f"[{now.isoformat()}]"

    print(get_current_time(), msg)


if __name__ == "__main__":
    run()