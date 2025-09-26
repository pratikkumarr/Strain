import streamlit as st
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
import re
import time
from urllib.parse import urlparse
import asyncio
import sys

# ----------------------------
# Fix Windows Playwright issue
# ----------------------------
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# ----------------------------
# Regex to find prices like ₹199 or Rs.199
# ----------------------------
PRICE_REGEX = re.compile(r"₹\s?[\d,]+|Rs\.?\s?[\d,]+")

def normalize_price_str(p):
    if not p: 
        return None
    p = re.sub(r"[^\d,]", "", p)
    p = p.replace(",", "")
    try:
        return int(p)
    except:
        return None

def find_nearest_price(text, item_name):
    prices = list(PRICE_REGEX.finditer(text))
    if not prices:
        return None, None
    item_pos = text.lower().find(item_name.lower()) if item_name else -1
    if item_pos == -1:
        return prices[0].group(0), prices[0].start()
    best = None
    best_dist = 10**9
    for m in prices:
        dist = abs(m.start() - item_pos)
        if dist < best_dist:
            best_dist = dist
            best = m
    return best.group(0), best.start() if best else (None, None)

def extract_from_page(page):
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except PWTimeout:
        pass
    title = page.title() or ""
    body_text = page.inner_text("body")
    price_match = PRICE_REGEX.search(title)
    if price_match:
        price_str = price_match.group(0)
    else:
        price_str, _ = find_nearest_price(body_text, title)
    return title, body_text, price_str

def scrape_platform(page, url, platform):
    page.goto(url, timeout=60000)
    title, body_text, price_str = extract_from_page(page)
    parts = [p.strip() for p in re.split(r"[\-\|–—:]", title) if p.strip()]
    if len(parts) >= 2:
        item_name, restaurant = parts[0], parts[1]
    elif len(parts) == 1:
        item_name, restaurant = parts[0], ""
    else:
        item_name, restaurant = title, ""
    if not price_str:
        price_search = PRICE_REGEX.search(body_text)
        price_str = price_search.group(0) if price_search else None
    return {"platform": platform, "url": url, "item": item_name.strip(), "restaurant": restaurant.strip(), "price_str": price_str}

def search_restaurant_on_platform(page, platform, restaurant_name):
    home = "https://www.zomato.com" if platform.lower() == "zomato" else "https://www.swiggy.com"
    page.goto(home, timeout=60000)
    try:
        page.wait_for_load_state("networkidle", timeout=8000)
    except PWTimeout:
        pass

    # Search input heuristics
    selectors = [
        "input[placeholder*='Search']",
        "input[type='search']",
        "input[aria-label*='search']",
        "input[placeholder*='Search for']",
        "input",
    ]
    search_input = None
    for s in selectors:
        try:
            loc = page.locator(s)
            if loc.count() > 0:
                search_input = loc.first
                break
        except:
            continue
    if not search_input:
        return None
    try:
        search_input.fill(restaurant_name)
        search_input.press("Enter")
    except:
        try:
            search_input.click()
            for ch in restaurant_name:
                search_input.type(ch)
            search_input.press("Enter")
        except:
            pass

    time.sleep(2)
    try:
        page.wait_for_load_state("networkidle", timeout=8000)
    except:
        pass

    # Click top search result
    anchors = page.locator("a")
    for i in range(min(anchors.count(), 20)):
        a = anchors.nth(i)
        try:
            txt = a.inner_text()
            if restaurant_name.lower() in txt.lower():
                href = a.get_attribute("href")
                if href and href.startswith("http"):
                    return href
        except:
            continue
    # fallback
    for i in range(min(anchors.count(), 5)):
        try:
            href = anchors.nth(i).get_attribute("href")
            if href and href.startswith("http"):
                return href
        except:
            continue
    return None

def search_item_in_restaurant(page, restaurant_url, item_name):
    page.goto(restaurant_url, timeout=60000)
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except:
        pass
    body = page.inner_text("body")
    price_str, _ = find_nearest_price(body, item_name)
    return price_str

def compare_prices(input_url):
    domain = urlparse(input_url).netloc.lower()

    # Guard against mobile deep-links
    if "onelink.me" in domain:
        return {"error": "❌ Please paste a full Zomato/Swiggy restaurant link from the web, not a mobile app link."}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # show browser for demo
        page = browser.new_page()
        if "zomato" in domain:
            src = scrape_platform(page, input_url, "Zomato")
            target_platform = "Swiggy"
        elif "swiggy" in domain:
            src = scrape_platform(page, input_url, "Swiggy")
            target_platform = "Zomato"
        else:
            browser.close()
            return {"error": "Only Zomato and Swiggy links supported."}

        # search restaurant & item on target platform
        rest_name = src["restaurant"] or src["item"]
        target_rest_url = search_restaurant_on_platform(page, target_platform, rest_name)
        target_price_str = None
        if target_rest_url:
            target_price_str = search_item_in_restaurant(page, target_rest_url, src["item"])
        target_price = normalize_price_str(target_price_str)

        src_price = normalize_price_str(src["price_str"])

        results = []
        results.append({"platform": src["platform"], "price": src_price, "link": src["url"]})
        results.append({"platform": target_platform, "price": target_price, "link": target_rest_url})

        available = [r for r in results if r["price"] is not None]
        cheapest = min(available, key=lambda x: x["price"]) if available else None
        browser.close()
        return {"results": results, "cheapest": cheapest}

# ----------------------------
# Streamlit UI
# ----------------------------
st.title("🍔 Price Comparison Agent (Real-Time)")
st.write("Paste a Zomato or Swiggy restaurant/item link from the website (not the mobile app). The agent finds the cheapest option in real-time.")

input_url = st.text_input("Enter Zomato or Swiggy link:")

if st.button("Compare Prices"):
    if not input_url:
        st.warning("Please enter a valid link.")
    else:
        with st.spinner("Fetching and comparing prices..."):
            data = compare_prices(input_url)
        if "error" in data:
            st.error(data["error"])
        else:
            st.subheader("Results")
            for r in data["results"]:
                price_display = f"₹{r['price']}" if r["price"] else "Not available"
                link_display = r["link"] if r["link"] else "Not found"
                st.write(f"{r['platform']}: {price_display} | [Link]({link_display})")
            if data["cheapest"]:
                st.success(f"✅ Cheapest: {data['cheapest']['platform']} at ₹{data['cheapest']['price']} | [Order here]({data['cheapest']['link']})")
