# 인터파크 2023 LOL 월드챔피언십 결승 취소표 예매 매크로

2023 LOL 월즈 결승전 취소표를 구하자...

- `Selenium`, `BeautifulSoup4`를 이용해서 인터파크 크롤링. 모바일 UI 이용.
- `OpenCV`, `pytesseract`를 이용해서 CAPTCHA 인식.

## 사용 방법

1. 레포 다운 후 필요한 프로그램 설치

   프로그램: **`Chrome`, `ChromeDriver`, `Python 3`**

   `ChromeDriver`는 `Chrome`과 버전 앞자리 수가 같아야 함 (예: Chrome 115.x <-> ChromeDriver 115.x). 현재 `static` 폴더 안에 있는 파일의 드라이버 버전은 [`개발 환경`](#개발-환경) 참조.

2. Python 패키지 설치

   ```shell
   pip install -r requirements.txt
   ```

3. `main.py` 에서 전역 변수들 설정

4. `main.py` 실행

   ```shell
   python main.py
   ```

## 주의점

- 좌석은 **자동 배정**.
- **결제하기** 버튼 클릭까지만 진행. 이후 결제는 직접 해야 함.
- **2023년 8월** 기준으로 코드를 작성했기 때문에, 사이트 구조가 바뀌면 작동하지 않을 수도 있음.

## 개발 환경

- 운영체제: `Windows 11 64bit 22H2`
- 브라우저: `Chrome 115.0.5790.171`
  - 드라이버: [`ChromeDriver 115.0.5790.170`](https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/115.0.5790.170/win64/chromedriver-win64.zip)
- 언어: [`Python 3.11.4`](https://www.python.org/downloads/release/python-3114/)
