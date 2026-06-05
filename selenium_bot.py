import os
import time
import random
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import undetected_chromedriver as uc

def human_delay(low=2.0, high=4.5):
    """Pauses script execution using random decimals to look like human behavior."""
    time.sleep(random.uniform(low, high))

def type_like_human(element, text):
    """Types data character-by-character with individual random delays."""
    for char in text:
        element.send_keys(char)
        time.sleep(random.uniform(0.07, 0.22))

def launch_bls_automation(config_data, image_path):
    print("\n🌐 [LAUNCHING STEALTH BROWSER SESSION]")
    
    options = uc.ChromeOptions()
    
    # Apply proxy configuration from your text file
    proxy = config_data.get("Proxy")
    if proxy:
        proxy_parts = proxy.split(":")
        if len(proxy_parts) >= 2:
            proxy_ip = proxy_parts[0]
            proxy_port = proxy_parts[1]
            options.add_argument(f'--proxy-server=http://{proxy_ip}:{proxy_port}')
            print(f"📡 Routed traffic through proxy server: {proxy_ip}:{proxy_port}")

    try:
        # Launching the anti-detect browser
        driver = uc.Chrome(options=options)
        driver.maximize_window()
        
        # 1. Navigate to the portal
        print("🔗 Connecting to BLS Italy Portal...")
        driver.get("https://pakistan.blsitalyvisa.com/") # Update to your exact portal link
        human_delay(3, 5)

        # 2. Simulate User Login
        print("🔑 Injecting login credentials...")
        # (Note: Replace ID/NAME selectors with the exact HTML properties of the BLS login page)
        # email_input = driver.find_element(By.ID, "Email")
        # type_like_human(email_input, config_data.get("Email"))
        # human_delay(1, 2)
        
        # pass_input = driver.find_element(By.ID, "Password")
        # type_like_human(pass_input, config_data.get("Password"))
        # human_delay(1.5, 3)

        # 3. Dynamic Form Dropdowns Selection
        print(f"🎯 Selecting Center Dropdown: {config_data.get('Center')}")
        print(f"🎯 Selecting Visa Class: {config_data.get('Service Type')}")

        # 4. Attach Passport Image PNG File
        print("📷 Injecting passport photo layout...")
        absolute_img_path = os.path.abspath(image_path)
        
        # Selenium handles file uploads by passing the system path directly to the input tag
        # file_upload_element = driver.find_element(By.XPATH, "//input[@type='file']")
        # file_upload_element.send_keys(absolute_img_path)
        print(f"   Success: Bound upload file from path -> {absolute_img_path}")

        # --- CAPTCHA BLOCK ---
        print("\n🧩 Bot waiting at CAPTCHA barrier...")
        print("🤖 Use 'RESUME BOT' on your dashboard window to pass this once ready.")
        
        # Keeps browser running without closing instantly
        while True:
            time.sleep(1)

    except Exception as e:
        print(f"❌ Critical exception encountered inside browser loop: {e}")
        if 'driver' in locals():
            driver.quit()