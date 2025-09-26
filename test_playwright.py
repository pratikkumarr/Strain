# test_playwright.py
from playwright.sync_api import sync_playwright
import time

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=80)  # headful so you can see what's happening
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
        )
        page = context.new_page()
        page.goto("https://www.swiggy.com/search?query=pizza", timeout=60000)
        print("Title:", page.title())
        # pause (opens Playwright inspector) — remove if it causes issues
        # page.pause()
        time.sleep(5)
        print("Page loaded. HTML length:", len(page.content()))
        browser.close()

if __name__ == "__main__":
    main()
