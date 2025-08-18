from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import sys

def screenshot_github(url, output="github.png"):
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
    driver.set_window_size(1920, 1080)  # HD resolution
    driver.get(url)
    driver.save_screenshot(output)
    driver.quit()
    print(f"Saved screenshot to {output}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python github_screenshot.py <GitHub URL> [output.png]")
    else:
        url = sys.argv[1]
        output = sys.argv[2] if len(sys.argv) > 2 else "github.png"
        screenshot_github(url, output)
