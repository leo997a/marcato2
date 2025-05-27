#!/bin/bash
# setup.sh
# إزالة ذاكرة التخزين المؤقت لـ webdriver_manager
rm -rf ~/.wdm

# تنزيل ChromeDriver الإصدار 120.0.6099.224 يدويًا
wget https://chromedriver.storage.googleapis.com/120.0.6099.224/chromedriver-linux64.zip
unzip chromedriver-linux64.zip
mv chromedriver-linux64/chromedriver /usr/local/bin/chromedriver
chmod +x /usr/local/bin/chromedriver
rm -rf chromedriver-linux64.zip chromedriver-linux64
