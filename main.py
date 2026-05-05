import os, sys, time, platform, requests, threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from seleniumbase import SB

# 从 GitHub Secrets 读取
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")
SERVER_IP = os.environ.get("FALIX_SERVER_IP")

TARGET_URL = "https://falixnodes.net/startserver"
OUTPUT_DIR = Path("output/screenshots")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 纯净的通知函数
def notify(ok: bool, msg: str, img: str = None):
    if not TG_BOT_TOKEN or not TG_CHAT_ID: return
    now = (datetime.now(timezone(timedelta(hours=8)))).strftime("%Y-%m-%d %H:%M:%S")
    text = f"🔔 FalixNodes: {'✅' if ok else '❌'}\n内容: {msg}\n时间: {now}"
    try:
        requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage", json={"chat_id": TG_CHAT_ID, "text": text}, timeout=10)
        if img and Path(img).exists():
            with open(img, "rb") as f:
                requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto", data={"chat_id": TG_CHAT_ID}, files={"photo": f}, timeout=15)
    except: pass

def main():
    if not SERVER_IP:
        print("Error: Missing FALIX_SERVER_IP"); sys.exit(1)

    # 启动虚拟桌面
    display = None
    if platform.system().lower() == "linux":
        from pyvirtualdisplay import Display
        display = Display(visible=False, size=(1920, 1080))
        display.start()

    with SB(uc=True, headed=False, locale="en", incognito=True) as sb:
        try:
            sb.set_window_size(1920, 1080)
            sb.uc_open_with_reconnect(TARGET_URL, reconnect_time=5.0)

            # 1. 解决隐私弹窗 (GDPR)
            time.sleep(3)
            if sb.is_element_visible('button[aria-label="Accept all"]'):
                sb.click('button[aria-label="Accept all"]')
                print("Privacy modal accepted.")
            elif sb.is_element_visible("button.fc-cta-consent"):
                sb.click("button.fc-cta-consent")
                print("Privacy modal (Alt) accepted.")

            # 2. CF 验证处理
            time.sleep(2)
            sb.uc_gui_click_captcha() 
            
            # 3. 填写 IP 并启动
            sb.wait_for_element_visible("#IP", timeout=20)
            sb.type("#IP", SERVER_IP)
            sb.scroll_to('button.btn-start')
            sb.click('button.btn-start')
            print("First button clicked.")

            # 4. 处理最后的二次确认确认按钮
            time.sleep(5)
            # 使用 JS 直接点击，防止被遮挡
            sb.wait_for_element_visible("#watchAdBtn", timeout=20)
            sb.execute_script('document.getElementById("watchAdBtn").click();')
            print("Final button clicked.")

            # 5. 结果反馈
            time.sleep(5)
            p = str(OUTPUT_DIR / "result.png")
            sb.save_screenshot(p)
            notify(True, f"服务器 {SERVER_IP} 续期成功", p)

        except Exception as e:
            p = str(OUTPUT_DIR / "error.png")
            sb.save_screenshot(p)
            notify(False, f"运行失败: {str(e)}", p)
            print(f"Error: {e}")

    if display: display.stop()

if __name__ == "__main__":
    main()
