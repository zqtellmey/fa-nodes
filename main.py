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
def notify(ok: bool, msg: str, img: str = None):
    if not TG_BOT_TOKEN or not TG_CHAT_ID: return
    # 使用香港/北京时间
    now = (datetime.now(timezone(timedelta(hours=8)))).strftime("%Y-%m-%d %H:%M:%S")
    text = f"🔔 FalixNodes: {'✅' if ok else '❌'}\n内容: {msg}\n时间: {now}"
    try:
        requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage", json={"chat_id": TG_CHAT_ID, "text": text}, timeout=10)
        if img and Path(img).exists():
            with open(img, "rb") as f:
                requests.post(f"https://api.telegram.org/bot{TG_CHAT_ID}/sendPhoto", data={"chat_id": TG_CHAT_ID}, files={"photo": f}, timeout=15)
    except: pass

def handle_turnstile(sb):
    """集成 Zampto 成功经验：精准检测 CF 验证框并点击"""
    try:
        time.sleep(2)
        # 检测是否需要验证 (寻找 cf-turnstile-response 隐藏域)
        result = sb.execute_script('return document.querySelector("input[name=\'cf-turnstile-response\']") !== null')
        if not result: 
            return True # 页面没有 CF 验证，直接通过
        
        print("[INFO] 检测到 CF 验证框，尝试点击...")
        sb.uc_gui_click_captcha() # 使用 UI 模拟点击
        time.sleep(5)
        return True
    except: 
        return False

def handle_privacy_modal(sb):
    """保留并强化隐私框处理"""
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

    # 启动虚拟桌面
    display = None
    if platform.system().lower() == "linux":
        from pyvirtualdisplay import Display
        display = Display(visible=False, size=(1920, 1080))
        display.start()

    # 使用 uc=True 进入特权模式
    with SB(uc=True, headed=False, locale="en", incognito=True) as sb:
        try:
            sb.set_window_size(1920, 1080)
            print(f"[INFO] 正在开启任务，目标 IP: {SERVER_IP}")
            
            # 使用带重连功能的打开
            sb.uc_open_with_reconnect(TARGET_URL, reconnect_time=5.0)

            # --- 核心改进：验证重试逻辑 ---
            success_loaded = False
            for attempt in range(3):
                handle_privacy_modal(sb) # 先清理可能挡住验证框的隐私弹窗
                handle_turnstile(sb)     # 处理 CF 验证
                
                try:
                    # 如果能看到 IP 输入框，说明验证通过
                    sb.wait_for_element_present("#IP", timeout=10)
                    print(f"[INFO] 验证通过 (尝试次数: {attempt + 1})")
                    success_loaded = True
                    break
                except:
                    print(f"[WARN] 第 {attempt + 1} 次尝试失败，正在刷新重试...")
                    sb.refresh()
                    time.sleep(3)

            if not success_loaded:
                raise Exception("无法通过 Cloudflare 验证或加载页面超时")

            # --- 步骤 3: 填写 IP 并启动 ---
            sb.type("#IP", SERVER_IP)
            sb.scroll_to('button.btn-start')
            sb.click('button.btn-start')
            print("First button clicked.")

            # --- 步骤 4: 处理最后的二次确认按钮 (watchAdBtn) ---
            time.sleep(5)
            # 再次清理可能出现的弹窗
            handle_privacy_modal(sb)
            
            sb.wait_for_element_visible("#watchAdBtn", timeout=20)
            # 使用 JS 点击以确保点击成功，不被遮挡
            sb.execute_script('document.getElementById("watchAdBtn").click();')
            print("Final button clicked. Starting 30s ad wait...")

            # --- 步骤 5: 等待 30 秒广告时间 ---
            for i in range(1, 4):
                time.sleep(10)
                print(f"Waiting... {i*10}s elapsed.")

            # --- 步骤 6: 结果反馈 ---
            p = str(OUTPUT_DIR / "result.png")
            sb.save_screenshot(p)
            notify(True, f"服务器 {SERVER_IP} 续期成功（含30s等待）", p)

        except Exception as e:
            p = str(OUTPUT_DIR / "error.png")
            sb.save_screenshot(p)
            notify(False, f"运行失败: {str(e)}", p)
            print(f"Error: {e}")

    if display: display.stop()

if __name__ == "__main__":
    main()
