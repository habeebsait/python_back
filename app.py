from flask import Flask, jsonify, request
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import Select
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
import time
import os

app = Flask(__name__)

def create_driver():
    chrome_options = ChromeOptions()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.binary_location = os.environ.get("CHROME_BINARY", "/usr/bin/google-chrome")
    return webdriver.Chrome(options=chrome_options)

def login_to_portal(driver, usn, day, month, year):
    """Common login function for both routes"""
    driver.get(url="https://parents.msrit.edu/newparents/")
    
    usn_field = driver.find_element(By.XPATH, value='//*[@id="username"]')
    usn_field.send_keys(usn)

    day_field = Select(driver.find_element(By.ID, "dd"))
    day_field.select_by_visible_text(day)

    month_field = Select(driver.find_element(By.ID, "mm"))
    month_field.select_by_value(month)

    year_field = Select(driver.find_element(By.ID, "yyyy"))
    year_field.select_by_value(year)

    login = driver.find_element(By.XPATH, value='//*[@id="login-form"]/div[3]/input[1]')
    login.click()

    # Wait for and click the initial button after login
    button = WebDriverWait(driver, 100).until(
        EC.element_to_be_clickable((By.XPATH, "/html/body/div[2]/div/p/button"))
    )
    button.click()

@app.route('/', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy"}), 200

@app.route('/attendance', methods=['GET'])
def get_attendance():
    driver = None
    try:
        usn = request.args.get('usn')
        dob = request.args.get('dob')
        print(f"Processing attendance request for USN: {usn}")

        if not usn or not dob:
            return jsonify({"error": "USN and DOB are required"}), 400

        year, month, day = dob.split('-')
        
        driver = create_driver()
        login_to_portal(driver, usn, day, month, year)

        # Scrape attendance data
        attendance_data = {}
        buttons = driver.find_elements(By.CLASS_NAME, "cn-attendanceclr")
        time.sleep(3)

        for i in range(len(buttons)):
            try:
                subject_name = driver.find_element(By.XPATH, value=f'//*[@id="page_bg"]/div[1]/div/div/div[5]/div/div/div/table/tbody/tr[{i+1}]/td[2]').text
                attendance = buttons[i].text

                # Scroll button into view
                try:
                    driver.execute_script("arguments[0].scrollIntoView(true);", buttons[i])
                except:
                    print(f"Scroll failed for subject {subject_name}")

                # Click attendance button
                button = WebDriverWait(driver, 100).until(
                    EC.element_to_be_clickable(buttons[i])
                )
                button.click()

                # Extract attendance details
                present_text = driver.find_element(By.XPATH, value='//*[@id="page_bg"]/div/div/div/div[5]/div[1]/div[2]/div/div[1]/div/div/span[1]').text
                present = int(present_text.split('[')[1].strip(']'))
                
                absent_text = driver.find_element(By.XPATH, value='//*[@id="page_bg"]/div/div/div/div[5]/div[1]/div[2]/div/div[1]/div/div/span[2]').text
                absent = int(absent_text.split('[')[1].strip(']'))
                
                remaining_text = driver.find_element(By.XPATH, value='//*[@id="page_bg"]/div/div/div/div[5]/div[1]/div[2]/div/div[1]/div/div/span[3]').text
                remaining = int(remaining_text.split('[')[1].strip(']'))

                # Calculate bunkable classes
                total_classes = present + absent + remaining
                can_bunk = total_classes * 0.25  # 25% attendance margin
                can_only_bunk = can_bunk - absent

                subject_data = {
                    "attendance": attendance,
                    "present": present,
                    "absent": absent,
                    "remaining": remaining,
                    "can_bunk": max(0, int(can_only_bunk)),
                    "total_classes": total_classes
                }
                attendance_data[subject_name] = subject_data

                # Navigate back and reset
                driver.back()
                button = WebDriverWait(driver, 100).until(
                    EC.element_to_be_clickable((By.XPATH, "/html/body/div[2]/div/p/button"))
                )
                button.click()
                buttons = driver.find_elements(By.CLASS_NAME, "cn-attendanceclr")

            except Exception as e:
                print(f"Error processing subject {i}: {str(e)}")
                continue

        return jsonify(attendance_data)

    except Exception as e:
        print(f"Error in attendance route: {str(e)}")
        return jsonify({"error": str(e)}), 500
    finally:
        if driver:
            driver.quit()

@app.route('/timetable', methods=['GET'])
def get_timetable():
    driver = None
    try:
        usn = request.args.get('usn')
        dob = request.args.get('dob')
        print(f"Processing timetable request for USN: {usn}")

        if not usn or not dob:
            return jsonify({"error": "USN and DOB are required"}), 400

        year, month, day = dob.split('-')
        
        driver = create_driver()
        login_to_portal(driver, usn, day, month, year)

        # Navigate to timetable section
        timetable_link = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//a[contains(text(), 'Time Table')]"))
        )
        timetable_link.click()

        # Wait for timetable to load
        time.sleep(2)

        # Initialize timetable data structure
        timetable_data = {
            "Monday": {},
            "Tuesday": {},
            "Wednesday": {},
            "Thursday": {},
            "Friday": {},
            "Saturday": {}
        }

        # Process each day
        for day in timetable_data.keys():
            try:
                # Find the row for the current day
                day_row = driver.find_element(By.XPATH, f"//tr[td[contains(text(), '{day}')]]")
                
                # Get all period cells for the day
                periods = day_row.find_elements(By.TAG_NAME, "td")[1:]  # Skip the day cell
                
                # Process each period
                for period_num, period in enumerate(periods, 1):
                    period_text = period.text.strip()
                    if period_text and period_text.lower() != "break":
                        timetable_data[day][f"Period {period_num}"] = period_text

            except Exception as e:
                print(f"Error processing {day}: {str(e)}")
                continue

        return jsonify(timetable_data)

    except Exception as e:
        print(f"Error in timetable route: {str(e)}")
        return jsonify({"error": str(e)}), 500
    finally:
        if driver:
            driver.quit()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)