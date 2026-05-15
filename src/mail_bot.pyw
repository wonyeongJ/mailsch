import poplib
import requests
import json
import time
import os
import urllib3
from pathlib import Path
from email.parser import Parser
from email.header import decode_header
from dotenv import load_dotenv

# .env 로드 및 설정
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
load_dotenv(ROOT_DIR / ".env")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

POP3_SERVER = 'webmail.a2m.co.kr'
EMAIL_USER = os.getenv('EMAIL_USER')
EMAIL_PW = os.getenv('EMAIL_PW')
MM_URL = 'https://chat.a2m.co.kr'
MMAUTHTOKEN = os.getenv('MMAUTHTOKEN')
MY_CHANNEL_ID = os.getenv('MY_CHANNEL_ID')

# 상태 체크용 변수
last_report_date = ""

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
        requests.post(f"{MM_URL}/api/v4/posts", headers=headers, json=payload, verify=False, timeout=10)
    except Exception as e:
        print(f"MM 전송 에러: {e}")

def check_and_notify():
    global last_report_date
    server = None
    
    # 1. 아침 8시 봇 상태 체크 보고
    current_time = time.localtime()
    today_str = time.strftime("%Y-%m-%d", current_time)
    if current_time.tm_hour == 8 and last_report_date != today_str:
        send_mm("☀️ **좋은 아침입니다!**\n사내메일 알림봇이 정상 작동 중입니다. 오늘도 즐거운 업무 되세요! 🚀")
        last_report_date = today_str

    try:
        # 2. 메일 서버 접속
        try:
            server = poplib.POP3_SSL(POP3_SERVER, 995, timeout=10)
        except:
            server = poplib.POP3(POP3_SERVER, 110, timeout=10)
            
        server.user(EMAIL_USER)
        server.pass_(EMAIL_PW)
        
        msg_count = len(server.list()[1])
        DATA_DIR.mkdir(exist_ok=True)
        last_idx_file = DATA_DIR / "last_idx.txt"
        
        if not os.path.exists(last_idx_file):
            with open(last_idx_file, "w") as f: f.write(str(msg_count))
            return

        with open(last_idx_file, "r") as f: last_idx = int(f.read().strip())

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
            
            with open(last_idx_file, "w") as f: f.write(str(msg_count))

    except Exception as e:
        print(f"에러 발생: {e}")
    finally:
        if server: server.quit()

if __name__ == "__main__":
    while True:
        check_and_notify()
        time.sleep(300) # 5분 간격
