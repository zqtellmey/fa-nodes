import os, sys, time, platform, requests, threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from seleniumbase import SB

# --- 1. 配置加载 (GitHub Secrets) ---
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")
SERVER_IP = os.environ.get("FALIX_SERVER_IP")
PROXY_SOCKS5 = os.environ.get("PROXY_SOCKS5")

TARGET_URL = "https://falixnodes.net/startserver"
OUTPUT_DIR = Path("output/screenshots")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 时区处理
CN_TZ = timezone(timedelta(hours=8))

# --- 2. 工具函数 ---
def cn_now() -> datetime: 
    return datetime.now(CN_TZ)

def cn_time_str() -> str: 
    return cn_now().strftime("%Y-%m-%d %H:%M:%S")

def shot(name: str) -> str: 
    return str(OUTPUT_DIR / f"{cn_now().strftime('%H%M%S')}-{name}.png")

def notify(ok: bool, msg: str, img: str = None):
    if not TG_BOT_TOKEN or not TG_CHAT_ID: return
    text = f"🔔 FalixNodes: {'✅' if ok else '❌'}\n内容: {msg}\n时间: {cn_time_str()}"
    try:
        requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage", 
                      json={"chat_id": TG_CHAT_ID, "text": text}, timeout=10)
        if img and Path(img).exists():
            with open(img, "rb") as f:
                requests.post(f"https://api.telegram.org/bot{TG_CHAT_ID}/sendPhoto", 
                              data={"chat_id": TG_CHAT_ID}, files={"photo": f}, timeout=15)
    except: pass

# --- 3. 核心验证模块 (深度集成 Zampto 逻辑) ---

def handle_turnstile(sb) -> bool:
    """参考 Zampto：检测并处理 CF Turnstile"""
    try:
        time.sleep(2)
        # 检测是否需要验证
        result = sb.execute_script('return document.querySelector("input[name=\'cf-turnstile-response\']") !== null')
        if not result: return True 
        
        print("[INFO] 尝试 Turnstile GUI 点击...")
        sb.uc_gui_click_captcha() 
        time.sleep(5)
        return True
    except: return False

def handle_privacy_modal(sb):
    """处理欧盟 GDPR 隐私询问弹窗 (针对 FalixNodes 优化)"""
    try:
        # 综合多种可能的隐私按钮选择器
        selectors = [
            "button.fc-cta-consent", 
            "button[aria-label='Accept all']", 
            "button:contains('Accept all')",
            ".fc-consent-root .fc-primary-button"
        ]
        for s in selectors:
            if sb.is_element_visible(s):
                sb.click(s)
                print(f"[INFO] 已点击隐私协议同意按钮: {s}")
                time.sleep(2)
                break
    except: pass

# --- 4. 主程序逻辑 ---

def main():
    if not SERVER_IP:
        print("[ERROR] 缺失 FALIX_SERVER_IP 环境变量"); sys.exit(1)

    display = None
    if platform.system().lower() == "linux":
        from pyvirtualdisplay import Display
        display = Display(visible=False, size=(1920, 1080))
        display.start()

    # 使用与 Zampto 类似的 UC 模式参数
    opts = {
        "uc": True, 
        "test": True, 
        "locale": "en", 
        "headed": False, 
        "incognito": True,
        "timeout_multiplier": 0.6 
    }
    if PROXY_SOCKS5: opts["proxy"] = PROXY_SOCKS5

    try:
        with SB(**opts) as sb:
            sb.set_window_size(1920, 1080)
            print(f"[INFO] 正在开启任务，目标 IP: {SERVER_IP}")
            
            # 1. 打开页面
            sb.uc_open_with_reconnect(TARGET_URL, reconnect_time=5.0)

            # 2. 增强型重试循环 (参考 Zampto 成功方案)
            success_loaded = False
            for attempt in range(3):
                # 关键：每次尝试都先清理隐私弹窗
                handle_privacy_modal(sb)
                # 然后处理 CF 打钩
                handle_turnstile(sb)
                
                try:
                    # 如果 IP 输入框出现了，说明 CF 和隐私弹窗都搞定了
                    sb.wait_for_element_present("#IP", timeout=10)
                    print(f"[INFO] 验证通过，进入主界面 (尝试次数: {attempt + 1})")
                    success_loaded = True
                    break
                except:
                    print(f"[WARN] 尝试 {attempt + 1}: 页面未就绪，保存快照并刷新...")
                    sb.save_screenshot(shot(f"retry_{attempt}"))
                    sb.refresh()
                    time.sleep(4)

            if not success_loaded:
                p = shot("cf_failed")
                sb.save_screenshot(p)
                notify(False, "验证失败", "经过 3 次尝试仍无法越过 CF 或隐私检查", p)
                return

            # 3. 填写 IP 并点击启动
            sb.type("#IP", SERVER_IP, timeout=5)
            sb.scroll_to('button.btn-start')
            sb.click('button.btn-start')
            print("[INFO] 已点击第一阶段启动按钮")

            # 4. 处理二次确认 (watchAdBtn)
            time.sleep(5)
            try:
                # 再次检测隐私弹窗（防止点击后二次弹出）
                handle_privacy_modal(sb)
                
                sb.wait_for_element_visible("#watchAdBtn", timeout=20)
                # 使用 JS 点击绕过任何可能的遮罩
                sb.execute_script('document.getElementById("watchAdBtn").click();')
                print("[INFO] 已点击确认启动按钮。开始 30s 广告等待...")
                
                # 5. 等待 30 秒广告时间
                for i in range(1, 4):
                    time.sleep(10)
                    print(f"Waiting... {i*10}s elapsed.")
                
                p = shot("success")
                sb.save_screenshot(p)
                notify(True, f"服务器 {SERVER_IP} 续期成功", p)
                
            except Exception as e:
                p = shot("popup_failed")
                sb.save_screenshot(p)
                notify(False, f"确认按钮处理失败: {str(e)}", p)

    except Exception as e:
        print(f"[FATAL] 脚本异常: {e}")
        notify(False, "脚本崩溃", str(e))
    finally:
        if display: display.stop()
        os._exit(0)

if __name__ == "__main__":
    # 启用 7 分钟看门狗
    threading.Timer(420, lambda: os._exit(0)).start()
    main()
