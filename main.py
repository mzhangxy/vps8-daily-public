import asyncio
import json
import os
import random
import re
import socket
import subprocess
import time
from urllib.parse import urlparse

import requests

from playwright.async_api import async_playwright


# ================= ENV =================

VPS8_BATCH = os.getenv("VPS8_BATCH", "")
VPS8_HY2_URL = os.getenv("VPS8_HY2_URL", "")

TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

SOCKS_PORT = 51080

EXT_PATH = os.path.abspath(
    "scripts/extensions/nopecha/unpacked"
)

SCREEN_DIR = "screenshots"

# 12分钟
HCAPTCHA_TIMEOUT = 360


# ================= 工具 =================

def ensure_screen_dir():
    os.makedirs(SCREEN_DIR, exist_ok=True)


def mask(email):
    return email[0] + "***"


def mask_ip(ip):
    try:
        p = ip.split(".")
        return f"{p[0]}.{p[1]}.*.*"
    except:
        return ip


async def snap(page, name):

    try:

        ensure_screen_dir()

        path = (
            f"{SCREEN_DIR}/"
            f"{int(time.time())}_{name}.png"
        )

        await page.screenshot(
            path=path,
            full_page=True
        )

        print("📸 截图:", path)

    except:
        pass


# ================= HY2 =================

def parse_hy2(url):

    u = url.replace("hysteria2://", "")

    parsed = urlparse("scheme://" + u)

    return {
        "server": f"{parsed.hostname}:{parsed.port}",
        "auth": parsed.username
    }


def wait_port(port):

    for _ in range(20):

        try:

            s = socket.create_connection(
                ("127.0.0.1", port),
                1
            )

            s.close()

            return True

        except:
            time.sleep(1)

    return False


def start_hy2():

    print("🚀 启动 HY2")

    cfg = parse_hy2(VPS8_HY2_URL)

    with open("/tmp/hy2.json", "w") as f:

        json.dump({
            "server": cfg["server"],
            "auth": cfg["auth"],
            "tls": {
                "insecure": True
            },
            "socks5": {
                "listen": f"127.0.0.1:{SOCKS_PORT}"
            }
        }, f)

    proc = subprocess.Popen(
        ["hysteria", "client", "-c", "/tmp/hy2.json"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    if not wait_port(SOCKS_PORT):
        raise Exception("HY2 启动失败")

    print("✅ HY2 已启动")

    return proc


# ================= TG =================

def send_tg(text):

    if not TELEGRAM_CHAT_ID or not TELEGRAM_BOT_TOKEN:
        return

    try:

        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text[:4000],
                "parse_mode": "HTML"
            },
            timeout=15
        )

    except Exception as e:

        print("⚠️ TG失败:", e)


# ================= IP =================

def check_ip():

    print("🌍 检测出口 IP")

    proxies = {
        "http": f"socks5h://127.0.0.1:{SOCKS_PORT}",
        "https": f"socks5h://127.0.0.1:{SOCKS_PORT}"
    }

    try:

        r = requests.get(
            "http://ip-api.com/json/?fields=query,countryCode",
            proxies=proxies,
            timeout=10
        )

        data = r.json()

        ip = f"{mask_ip(data['query'])} ({data['countryCode']})"

        print("🌍 出口 IP:", ip)

        return ip

    except Exception as e:

        print("⚠️ IP检测失败:", e)

        return "未知IP"


# ================= 真人模拟 =================

async def human_like(page):

    try:

        for _ in range(random.randint(2, 5)):

            await page.mouse.move(
                random.randint(100, 1200),
                random.randint(100, 800),
                steps=random.randint(5, 20)
            )

            await asyncio.sleep(
                random.uniform(0.2, 1)
            )

        await page.mouse.wheel(
            0,
            random.randint(200, 1000)
        )

    except:
        pass


# ================= 扩展检测 =================

async def wait_extension_loaded(context):

    print("🧩 等待 NopeCHA 加载")

    for _ in range(60):

        try:

            sw = context.service_workers
            bg = context.background_pages

            if len(sw) > 0 or len(bg) > 0:

                print("✅ NopeCHA 已加载")

                return True

        except:
            pass

        await asyncio.sleep(1)

    return False


# ================= hCaptcha =================

async def solve_hcaptcha(page):

    print("🤖 检测 hCaptcha")

    try:

        iframe_count = await page.locator(
            'iframe[src*="hcaptcha.com"]'
        ).count()

        if iframe_count == 0:

            print("ℹ️ 未发现 hCaptcha")

            return True

    except:
        return True

    print("⏳ 等待 NopeCHA 自动处理（最长12分钟）")

    start = time.time()

    while time.time() - start < HCAPTCHA_TIMEOUT:

        elapsed = int(time.time() - start)

        print(
            f"⏳ NopeCHA 工作中..."
            f" 已等待 {elapsed}s"
        )

        try:

            iframe_count = await page.locator(
                'iframe[src*="hcaptcha.com"]'
            ).count()

            if iframe_count == 0:

                print("✅ hCaptcha iframe 已消失")

                return True

        except:
            pass

        # token 检测
        try:

            token = await page.evaluate("""
                () => {
                    const el = document.querySelector(
                        'textarea[name="h-captcha-response"]'
                    );
                    return el ? el.value : "";
                }
            """)

            if token and len(token) > 20:

                print("✅ hCaptcha token 已生成")

                return True

        except:
            pass

        try:

            body = await page.text_content("body")

            if body:

                low = body.lower()

                if any(k in low for k in [
                    "verification successful",
                    "challenge passed",
                    "you are verified",
                    "success"
                ]):

                    print("✅ hCaptcha 已通过")

                    return True

        except:
            pass

        await asyncio.sleep(2)

    print("⚠️ hCaptcha 超时")

    await snap(page, "hcaptcha_timeout")

    return False


# ================= 登录判断 =================

async def is_logged_in(page):

    try:

        url = page.url

        if (
            "vps8.zz.cd" in url
            and "/login" not in url
        ):
            return True

        body = await page.text_content("body")

        if body and any(k in body for k in [
            "退出",
            "Dashboard",
            "控制台",
            "Welcome"
        ]):
            return True

    except:
        pass

    return False


# ================= 积分 =================

async def get_points(page):

    try:

        txt = await page.text_content("body")

        m = re.search(
            r"当前积分.*?(\d+)",
            txt
        )

        return m.group(1) if m else "未知"

    except:
        return "未知"


# ================= 登录签到 =================

async def login_and_signin(page, email, password):

    print(f"\n👉 当前账号: {mask(email)}")

    await page.goto(
        "https://vps8.zz.cd/login",
        wait_until="domcontentloaded"
    )

    await asyncio.sleep(3)

    await human_like(page)

    print("✍️ 输入邮箱")

    await page.fill("#email", email)

    await asyncio.sleep(random.uniform(1, 2))

    print("🔒 输入密码")

    await page.fill("#password", password)

    await asyncio.sleep(random.uniform(1, 2))

    ok = await solve_hcaptcha(page)

    if not ok:
        return False, "验证码失败", "0"

    await asyncio.sleep(
        random.uniform(2, 5)
    )

    print("🚀 提交登录")

    try:

        await page.click(
            'button[type="submit"]'
        )

    except:

        await page.evaluate("""
            document.querySelector('button[type="submit"]').click()
        """)

    for _ in range(30):

        await asyncio.sleep(1)

        print("🔎 URL:", page.url)

        if await is_logged_in(page):

            print("✅ 登录成功")

            break

    else:

        await snap(page, f"{mask(email)}_login_fail")

        return False, "登录失败", "0"

    print("🎯 进入签到页")

    await page.goto(
        "https://vps8.zz.cd/points/signin",
        wait_until="domcontentloaded"
    )

    await asyncio.sleep(3)

    body = await page.text_content("body")

    if body and "已签到" in body:

        return True, "已签到", await get_points(page)

    ok = await solve_hcaptcha(page)

    if not ok:
        return False, "签到验证码失败", "0"

    await asyncio.sleep(2)

    print("🚀 提交签到")

    try:

        await page.click("#points-signin-submit")

    except:

        await page.evaluate("""
            document.querySelector("#points-signin-submit").click()
        """)

    await asyncio.sleep(5)

    return True, "签到成功", await get_points(page)


# ================= MAIN =================

async def main():

    ensure_screen_dir()

    report = "📋 <b>VPS8 签到报告</b>\n\n"

    hy2 = None

    try:

        hy2 = start_hy2()

        ip = check_ip()

        report += f"🌍 出口IP: {ip}\n\n"

        user_data_dir = "/tmp/pw-vps8-profile"

        async with async_playwright() as p:

            context = await p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=False,
                viewport={
                    "width": 1366,
                    "height": 900
                },
                locale="en-US",
                proxy={
                    "server": f"socks5://127.0.0.1:{SOCKS_PORT}"
                },
                args=[
                    f"--disable-extensions-except={EXT_PATH}",
                    f"--load-extension={EXT_PATH}",
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage"
                ]
            )

            context.set_default_timeout(180000)

            ok = await wait_extension_loaded(context)

            if not ok:
                raise Exception("NopeCHA 扩展加载失败")

            page = await context.new_page()

            for acc in VPS8_BATCH.split(","):

                if not acc.strip():
                    continue

                try:

                    email, password = acc.split(":")

                    ok, sign, points = await login_and_signin(
                        page,
                        email,
                        password
                    )

                    report += (
                        f"👤 {mask(email)}\n"
                        f"✅ {sign}\n"
                        f"💰 积分: {points}\n\n"
                    )

                except Exception as e:

                    print("💥", e)

                    await snap(
                        page,
                        f"{mask(email)}_error"
                    )

                    report += (
                        f"💥 {mask(email)}\n"
                        f"<code>{str(e)}</code>\n\n"
                    )

            await context.close()

    except Exception as e:

        report += (
            f"❌ 全局错误\n"
            f"<code>{str(e)}</code>"
        )

    send_tg(report)

    if hy2:
        hy2.kill()


if __name__ == "__main__":
    asyncio.run(main())
