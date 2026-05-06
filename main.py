import os, sys, time, platform, requests, threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from seleniumbase import SB

# --- 1. 配置加载 (从 GitHub Secrets 读取) ---
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")
SERVER_IP = os.environ.get("FALIX_SERVER_IP")

TARGET_URL = "https://falixnodes.net/startserver"
OUTPUT_DIR = Path("output/screenshots")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# --- 2. 工具函数 ---
def notify(ok: bool, msg: str, img_path: str = None):
    """
    发送文本通知，如果提供 img_path 则同时发送截图
    """
    if not TG_BOT_TOKEN or not TG_CHAT_ID: 
        print("[WARN] 缺少 TG 配置，跳过通知")
        return
        
    now = (datetime.now(timezone(timedelta(hours=8)))).strftime("%Y-%m-%d %H:%M:%S")
    status_icon = "✅" if ok else "❌"
    text = f"🔔 FalixNodes: {status_icon}\n内容: {msg}\n时间: {now}"
    
    try:
        # 1. 发送文字消息
        requests.post(
            f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage", 
            json={"chat_id": TG_CHAT_ID, "text": text}, 
            timeout=10
        )
        
        # 2. 如果有图片且文件存在，发送图片
        if img_path and Path(img_path).exists():
            with open(img_path, "rb") as f:
                requests.post(
                    f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto", 
                    data={"chat_id": TG_CHAT_ID}, 
                    files={"photo": f}, 
                    timeout=15
                )
            print(f"[INFO] 截图已发送: {img_path}")
    except Exception as e:
        print(f"[ERROR] TG 通知发送失败: {e}")

def handle_turnstile(sb):
    """集成 Zampto 成功经验：精准检测 CF 验证框并点击"""
    try:
        time.sleep(2)
        result = sb.execute_script('return document.querySelector("input[name=\'cf-turnstile-response\']") !== null')
        if not result: 
            return True 
        
        print("[INFO] 检测到 CF 验证框，尝试点击...")
        sb.uc_gui_click_captcha() 
        time.sleep(5)
        return True
    except: 
        return False

def handle_privacy_modal(sb):
    """处理隐私框逻辑"""
    try:
        selectors = ["button[aria-label='Accept all']", "button.fc-cta-consent"]
        for s in selectors:
            if sb.is_element_visible(s):
                sb.click(s)
                print(f"[INFO] 已接受隐私协议: {s}")
                time.sleep(2)
                break
    except: pass

# --- 3. 主程序逻辑 ---
def main():
    if not SERVER_IP:
        print("Error: Missing FALIX_SERVER_IP"); sys.exit(1)

    display = None
    if platform.system().lower() == "linux":
        from pyvirtualdisplay import Display
        display = Display(visible=False, size=(1920, 1080))
        display.start()

    with SB(uc=True, headed=False, locale="en", incognito=True) as sb:
        try:
            sb.set_window_size(1920, 1080)
            print(f"[INFO] 正在开启任务，目标 IP: {SERVER_IP}")
            sb.uc_open_with_reconnect(TARGET_URL, reconnect_time=5.0)

            # 验证重试逻辑
            success_loaded = False
            for attempt in range(3):
                handle_privacy_modal(sb)
                handle_turnstile(sb)
                
                try:
                    sb.wait_for_element_present("#IP", timeout=10)
                    print(f"[INFO] 验证通过 (尝试次数: {attempt + 1})")
                    success_loaded = True
                    break
                except:
                    print(f"[WARN] 第 {attempt + 1} 次尝试失败，正在刷新重试...")
                    sb.refresh()
                    time.sleep(3)

            if not success_loaded:
                error_img = str(OUTPUT_DIR / "cf_error.png")
                sb.save_screenshot(error_img)
                notify(False, "无法越过 Cloudflare 验证", error_img)
                return

            # 填写 IP 并启动
            sb.type("#IP", SERVER_IP)
            sb.scroll_to('button.btn-start')
            sb.click('button.btn-start')
            
            # 处理二次确认
            time.sleep(5)
            handle_privacy_modal(sb)
            
            sb.wait_for_element_visible("#watchAdBtn", timeout=20)
            sb.execute_script('document.getElementById("watchAdBtn").click();')
            print("[INFO] 最终按钮已点击，开始 30s 广告等待...")

            # 等待 30 秒广告
            for i in range(1, 4):
                time.sleep(10)
                print(f"Waiting... {i*10}s elapsed.")

            # 成功截图并发送
            success_img = str(OUTPUT_DIR / "success.png")
            sb.save_screenshot(success_img)
            notify(True, f"服务器 {SERVER_IP} 续期成功", success_img)

        except Exception as e:
            error_img = str(OUTPUT_DIR / "exception.png")
            sb.save_screenshot(error_img)
            notify(False, f"程序异常: {str(e)}", error_img)
            print(f"Error: {e}")

    if display: display.stop()

if __name__ == "__main__":
    main()
