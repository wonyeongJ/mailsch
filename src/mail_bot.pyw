import poplib
import requests
import time
import os
import urllib3
import logging
import sys
import argparse
from pathlib import Path
from email.parser import Parser
from email.header import decode_header
from dotenv import load_dotenv

# .env 로드 및 설정
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
LOG_DIR = DATA_DIR / "logs"
LOG_FILE = LOG_DIR / "run_bot.log"
load_dotenv(ROOT_DIR / ".env")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

POP3_SERVER = 'webmail.a2m.co.kr'
EMAIL_USER = os.getenv('EMAIL_USER')
EMAIL_PW = os.getenv('EMAIL_PW')
MM_URL = 'https://chat.a2m.co.kr'
MMAUTHTOKEN = os.getenv('MMAUTHTOKEN')
MY_CHANNEL_ID = os.getenv('MY_CHANNEL_ID')
LAST_IDX_FILE = DATA_DIR / "last_idx.txt"

# 상태 체크용 변수
last_report_date = ""

def setup_logging():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handlers = [logging.FileHandler(LOG_FILE, encoding="utf-8")]
    if sys.stdout:
        handlers.append(logging.StreamHandler(sys.stdout))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers,
    )

def validate_config():
    missing = [
        name for name, value in {
            "EMAIL_USER": EMAIL_USER,
            "EMAIL_PW": EMAIL_PW,
            "MMAUTHTOKEN": MMAUTHTOKEN,
            "MY_CHANNEL_ID": MY_CHANNEL_ID,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(
            ".env 설정이 비어 있습니다: "
            + ", ".join(missing)
            + " 값을 확인해 주세요."
        )

def get_decode_text(header_value):
    if not header_value: return ""
    decoded = decode_header(header_value)
    result = ""
    for content, charset in decoded:
        if isinstance(content, bytes):
            result += content.decode(charset if charset else 'utf-8', errors='replace')
        else: result += content
    return result

def send_mm(message):
    """메타모스트 전송 공통 함수"""
    headers = {
        'Cookie': f'MMAUTHTOKEN={MMAUTHTOKEN}',
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest'
    }
    payload = {
        "channel_id": MY_CHANNEL_ID,
        "username": "사내메일 알림봇",
        "message": message,
        "props": {
            "from_webhook": "true",
            "override_username": "사내메일 알림봇",
            "override_icon_url": "https://cdn-icons-png.flaticon.com/512/6125/6125845.png"
        }
    }
    try:
        response = requests.post(f"{MM_URL}/api/v4/posts", headers=headers, json=payload, verify=False, timeout=10)
        response.raise_for_status()
        logging.info("Mattermost 알림 전송 성공: HTTP %s", response.status_code)
    except Exception as e:
        logging.exception("Mattermost 알림 전송 실패: %s", e)

def read_last_idx(default_idx):
    try:
        return int(LAST_IDX_FILE.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        LAST_IDX_FILE.write_text(str(default_idx), encoding="utf-8")
        return default_idx

def parse_args():
    parser = argparse.ArgumentParser(description="사내메일 Mattermost 알림봇")
    parser.add_argument(
        "--check-once",
        action="store_true",
        help="환경 설정과 메일 서버 로그인을 1회 확인한 뒤 종료합니다.",
    )
    return parser.parse_args()

def check_mail_connection():
    server = None
    try:
        try:
            logging.info("POP3 SSL 접속 시도: %s:995", POP3_SERVER)
            server = poplib.POP3_SSL(POP3_SERVER, 995, timeout=10)
        except Exception as ssl_error:
            logging.warning("POP3 SSL 접속 실패, 일반 POP3로 재시도합니다: %s", ssl_error)
            server = poplib.POP3(POP3_SERVER, 110, timeout=10)

        server.user(EMAIL_USER)
        server.pass_(EMAIL_PW)
        msg_count = len(server.list()[1])
        logging.info("메일 서버 로그인 및 목록 조회 성공: %s, 전체 %s건", EMAIL_USER, msg_count)
    finally:
        if server:
            try:
                server.quit()
            except Exception:
                pass

def check_and_notify(raise_errors=False, send_daily_report=True):
    global last_report_date
    server = None
    
    # 1. 아침 8시 봇 상태 체크 보고
    current_time = time.localtime()
    today_str = time.strftime("%Y-%m-%d", current_time)
    if send_daily_report and current_time.tm_hour == 8 and last_report_date != today_str:
        send_mm("☀️ **좋은 아침입니다!**\n사내메일 알림봇이 정상 작동 중입니다. 오늘도 즐거운 업무 되세요! 🚀")
        last_report_date = today_str

    try:
        # 2. 메일 서버 접속
        try:
            logging.info("POP3 SSL 접속 시도: %s:995", POP3_SERVER)
            server = poplib.POP3_SSL(POP3_SERVER, 995, timeout=10)
        except Exception as ssl_error:
            logging.warning("POP3 SSL 접속 실패, 일반 POP3로 재시도합니다: %s", ssl_error)
            server = poplib.POP3(POP3_SERVER, 110, timeout=10)
            
        server.user(EMAIL_USER)
        server.pass_(EMAIL_PW)
        logging.info("메일 서버 로그인 성공: %s", EMAIL_USER)
        
        msg_count = len(server.list()[1])
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        last_idx = read_last_idx(msg_count)
        logging.info("메일함 확인 완료: 전체 %s건, 마지막 처리 %s건", msg_count, last_idx)

        if msg_count < last_idx:
            LAST_IDX_FILE.write_text(str(msg_count), encoding="utf-8")
            return

        # 3. 새 메일 확인 및 알림 전송
        if msg_count > last_idx:
            for i in range(last_idx + 1, msg_count + 1):
                _, lines, _ = server.retr(i)
                msg_content = b'\n'.join(lines).decode('utf-8', errors='ignore')
                mail = Parser().parsestr(msg_content)
                subject = get_decode_text(mail['Subject'])
                sender = get_decode_text(mail['From'])

                # 바로가기 링크 (로그인 상태 시 메인프레임으로 진입)
                mail_link = "https://webmail.a2m.co.kr/mail/mainframe"
                
                msg = (
                    f"🤖 **새 메일이 도착했습니다**\n"
                    f"---\n"
                    f"- **보낸사람**: {sender}\n"
                    f"- **제목**: {subject}\n\n"
                    f"[👉 메일함 확인하기]({mail_link})"
                )
                send_mm(msg)
            
            LAST_IDX_FILE.write_text(str(msg_count), encoding="utf-8")
            logging.info("새 메일 %s건 처리 완료", msg_count - last_idx)

    except Exception as e:
        logging.exception("메일 확인 중 에러 발생: %s", e)
        if raise_errors:
            raise
    finally:
        if server:
            try:
                server.quit()
            except Exception:
                pass

if __name__ == "__main__":
    args = parse_args()
    setup_logging()
    logging.info("메일 알림봇을 시작합니다. 프로젝트 경로: %s", ROOT_DIR)
    logging.info("로그 파일: %s", LOG_FILE)
    try:
        validate_config()
    except Exception as e:
        logging.exception("시작 전 설정 확인 실패: %s", e)
        sys.exit(2)

    if args.check_once:
        try:
            check_mail_connection()
            logging.info("1회 점검이 정상 완료되었습니다.")
            sys.exit(0)
        except Exception:
            sys.exit(3)

    try:
        while True:
            check_and_notify()
            time.sleep(300) # 5분 간격
    except KeyboardInterrupt:
        logging.info("사용자 요청으로 종료합니다.")
        sys.exit(0)
    except Exception as e:
        logging.exception("예상하지 못한 치명적 에러로 종료합니다: %s", e)
        sys.exit(1)
