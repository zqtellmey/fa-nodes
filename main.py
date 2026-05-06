import os, sys, time, platform, requests
from datetime import datetime, timezone, timedelta
from pathlib import Path
from seleniumbase import SB

# --- 1. 配置加载 ---
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")
# 优先获取手动输入的 IP
SERVER_IP = os.environ.get("FALIX_SERVER_IP") or "yaho.falixsrv.me"

TARGET_URL = "https://falixnodes.net/startserver"
OUTPUT_DIR = Path("output/screenshots")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# --- 2. 工具函数 ---
def notify(ok: bool, msg: str, img_path: str = None):
    if not TG_BOT_TOKEN or not TG_CHAT_ID: 
        print(f"[DEBUG] {msg}")
        return
    now = (datetime.now(timezone(timedelta(hours=8)))).strftime("%Y-%m-%d %H:%M:%S")
    status_icon = "✅" if ok else "❌"
    text = f"🔔 FalixNodes: {status_icon}\n内容: {msg}\n时间: {now}"
    try:
        requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage", json={"chat_id": TG_CHAT_ID, "text": text}, timeout=10)
        if img_path and Path(img_path).exists():
            with open(img_path, "rb") as f:
                requests.post(f"https://api.telegram.org/bot{TG_CHAT_ID}/sendPhoto", data={"chat_id": TG_CHAT_ID}, files={"photo": f}, timeout=15)
    except Exception as e:
        print(f"[ERROR] TG 通知失败: {e}")

# --- 3. 主程序逻辑 ---
def main():
    display = None
    if platform.system().lower() == "linux":
        from pyvirtualdisplay import Display
        display = Display(visible=False, size=(1920, 1080))
        display.start()

    # uc=True 模式会自动处理 Cookies 和复杂的浏览器指纹
    with SB(uc=True, headed=False, locale="en", incognito=True) as sb:
        try:
            sb.set_window_size(1920, 1080)
            print(f"[INFO] 任务启动，目标 IP: {SERVER_IP}")
            
            # 1. 打开页面并获取会话状态 (Cookies/Referer 基础)
            sb.uc_open_with_reconnect(TARGET_URL, reconnect_time=5.0)
            
            # 2. 处理验证码 (使用你指定的坐标 835, 583)
            time.sleep(3)
            if sb.is_element_present('input[name="cf-turnstile-response"]'):
                print(f"[INFO] 点击验证码坐标...")
                sb.click_with_offset("body", 835, 583)
                time.sleep(5)

            # 3. 激活广告逻辑 (必须先点这个，后端才会允许 POST)
            sb.wait_for_element_visible("#watchAdBtn", timeout=20)
            sb.execute_script('document.getElementById("watchAdBtn").click();')
            print("[INFO] 广告按钮已点击，等待 40 秒模拟播放...")
            
            for i in range(1, 5):
                time.sleep(10)
                print(f"Waiting... {i*10}s")

            # 4. 核心：高度模拟抓包数据的 Fetch POST
            # 浏览器会自动补全：referer, origin, cookie, user-agent, sec-ch-ua 等
            print(f"[INFO] 正在以相同 Referer 模拟 POST 启动服务器...")
            post_script = f"""
            fetch('/startserver', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                    'Cache-Control': 'max-age=0'
                }},
                body: 'IP={SERVER_IP}&cf-turnstile-response=',
                referrer: '{TARGET_URL}',
                referrerPolicy: 'strict-origin-when-cross-origin',
                mode: 'cors',
                credentials: 'include'
            }}).then(response => {{
                if (response.redirected) {{
                    window.location.href = response.url;
                }} else {{
                    location.reload();
                }}
            }}).catch(err => {{
                console.error('Fetch Error:', err);
            }});
            """
            sb.execute_script(post_script)
            
            # 5. 等待跳转刷新
            time.sleep(10)
            
            # 6. 判定最终结果
            if sb.is_element_visible('#success-alert'):
                msg = sb.get_text("#success-msg")
                p_ok = str(OUTPUT_DIR / "final_success.png")
                sb.save_screenshot(p_ok)
                notify(True, f"通过模拟 POST 成功开启: {msg}", p_ok)
            else:
                p_fail = str(OUTPUT_DIR / "final_fail_status.png")
                sb.save_screenshot(p_fail)
                notify(False, "POST 请求未触发成功页面，请检查截图", p_fail)

        except Exception as e:
            notify(False, f"程序运行异常: {str(e)}")

    if display: display.stop()

if __name__ == "__main__":
    main()
