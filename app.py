from collections import defaultdict
from mysql.connector import Error
from dotenv import load_dotenv
from datetime import datetime
import mysql.connector
from os import getenv
import requests
import logging
import socket
import time
import json
import re

interval,measurement_interval = 0,0
lst_request_time = 0

load_dotenv()


def load_config():
    global interval,measurement_interval
    with open('data/config.json') as f:
        d = json.load(f)['config']
        interval = d['server-time-get']
        measurement_interval = d['device-time-measurement']


logger = logging.getLogger(__name__)


def set_format():
    formatter = [logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'),logging.Formatter('%(asctime)s - %(message)s')]
    logger.setLevel(logging.INFO)
    file_handler = logging.FileHandler('data/app.log')
    file_handler.setLevel(logging.ERROR)
    file_handler.setFormatter(formatter[0])

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter[1])

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)


load_config()
lst_values = [interval,measurement_interval]
set_format()
interval_betweenjson_load = 5000
lst_measure = time.time()
esp_devices = []
lst_check = 0
get_all_devices = 0
UDP_IP = ""
UDP_PORT = 4210
entry_time = 0
lst_device_upload = time.time()
lst_request_times = {}
DATABASE_HOST: str = getenv('DATABASE_HOST')
DATABASE_PORT: int = int(getenv('DATABASE_PORT'))
DATABASE_USER: str = getenv('DATABASE_USER')
DATABASE_PASSWORD: str = getenv('DATABASE_PASSWORD')
DATABASE: str = getenv('DATABASE')
exce = []
disconnect = False
try:
    esp_db = mysql.connector.connect(
        host=DATABASE_HOST,
        port=DATABASE_PORT,
        user=DATABASE_USER,
        password=DATABASE_PASSWORD,
        database=DATABASE
    )
    esp_cursor = esp_db.cursor()

except Error as e:
    logger.error(f"Error connecting to MySQL database: {e}")
    exit()


def get_database() -> None:
    global esp_db, esp_cursor
    try:
        esp_db = mysql.connector.connect(
            host=DATABASE_HOST,
            port=DATABASE_PORT,
            user=DATABASE_USER,
            password=DATABASE_PASSWORD,
            database=DATABASE
        )
        esp_cursor = esp_db.cursor()
    except Error as e:
        print(f"Error connecting to MySQL database: {e}")


def insert_data(temp, timestamp, sensor_id):
    b: str = ''
    try:
        get_database()
        global esp_db, esp_cursor
        esp_cursor.execute("SELECT MAX(id) FROM temp_data")
        max_id = esp_cursor.fetchone()[0]
        index = (max_id + 1) if max_id is not None else 1

        esp_cursor.execute("INSERT INTO temp_data (id, temp, time, sensor_id) VALUES (%s, %s, %s, %s)",
                           (index, temp, timestamp, sensor_id))
        esp_db.commit()

    except Error as b:
        logger.error(f"Error inserting data: {b}")


def get_data(sensor_id):
    b: str = ''
    try:
        get_database()
        global esp_db, esp_cursor
        query = """
        SELECT UNIX_TIMESTAMP(time) AS timestamp, COUNT(*)
        FROM temp_data
        WHERE sensor_id = %s
        GROUP BY timestamp
        HAVING COUNT(*) > 1
        """
        esp_cursor.execute(query, (sensor_id,))
        duplicates = esp_cursor.fetchall()
        return duplicates
    except Error as b:
        logger.error(f"Error retrieving data: {b}")
        return []


def get_esp8266_temp(ip: str, start_time: dict, max_retries=3):
    global esp_devices, exce
    retry_count = 0

    while retry_count < max_retries:
        try:
            url = f"http://{ip}/temp?time={int(round(time.time() - min(start_time.values()))) + 10}&limit=50"
            response = requests.get(url)
            response.raise_for_status()
            response_data = response.json()
            break
        except Exception as b:
            retry_count += 1
            if retry_count == max_retries:
                logger.error(f"Max retries reached for {ip}. Disconnecting device")
                _disconnect_device(ip)
                return False

    temperatures = response_data.get("temperature_data", [])
    remain = response_data.get("remain_cnt", 0)
    curr_time = time.time()

    rec = []
    for record in temperatures:
        temperature = record['temp']
        entry_time = record['time']
        sensor_id = record['sensor_id']
        if curr_time - entry_time / 1000 > start_time.get(sensor_id, 0):
            lst_request_times[sensor_id] = curr_time - entry_time / 1000

        time_date = datetime.fromtimestamp(curr_time - entry_time / 1000).strftime("%Y-%m-%d %H:%M:%S")

        esp_cursor.execute(
            "SELECT COUNT(*) FROM temp_data WHERE sensor_id = %s AND time = %s",
            (sensor_id, time_date)
        )
        if esp_cursor.fetchone()[0] == 0 and int(temperature) != -127:
            insert_data(temperature, time_date, sensor_id)
            if not any(sensor[0] == sensor_id for sensor in rec):
                rec.append((sensor_id, 1))
            else:
                for i in range(len(rec)):
                    if rec[i][0] == sensor_id:
                        rec[i] = (sensor_id, rec[i][1] + 1)
    rec = sorted(rec, key=lambda x: x[0])

    message = ', '.join(f'sensor {sensor_id}: {count} rec' for sensor_id, count in rec)
    if message != '':
        logger.info(f"Read {message}, remaining {remain} records from sensors")

    if remain > 0:
        retry_count = 0
        while retry_count < max_retries:
            try:
                return get_esp8266_temp(ip, lst_request_times)
            except Exception:
                retry_count += 1
                if retry_count == max_retries:
                    logger.error(f"Max retries reached for {ip}. Disconnecting device")
                    _disconnect_device(ip)
                    return False


def _disconnect_device(ip: str):
    global esp_devices, exce, disconnect

    try:
        while True:
            response = requests.get(f"http://{ip}/exit")
            if response.status_code == 200:
                logger.info(f"Device {ip} was reset")
                return True
            else:
                logger.error("Device not responding. Try to restart device.")
                esp_devices = [item for item in esp_devices if item[0] != ip]
                disconnect = True
                return False
    except Exception:
        logger.error("Device not responding. Try to restart device.")
        esp_devices = [item for item in esp_devices if item[0] != ip]
        disconnect = True
        return False


def first_request(ip: str):
    get_database()
    global entry_time, lst_request_times,esp_devices
    try:
        url = f"http://{ip}/temp"
        response = requests.get(url)
        if response.status_code != 200:
            logger.warning(f"Failed to get data from {ip}. Status code: {response.status_code}")
            return False

    except Exception as b:
        logger.error(f"Error requesting data from {ip}: {str(b)}")
        _disconnect_device(ip)
        return False

    response = response.json()
    remain = response["remain_cnt"]
    temperatures = response["temperature_data"]
    curr_time = time.time()

    rec = []
    for record in temperatures:
        sensor = record['sensor_id']
        temperature = record['temp']
        entry_time = record['time']

        if sensor not in lst_request_times:
            lst_request_times[sensor] = 0

        if entry_time > lst_request_times[sensor]:
            lst_request_times[sensor] = curr_time - entry_time / 1000

        time_date = datetime.fromtimestamp(curr_time - entry_time / 1000).strftime("%Y-%m-%d %H:%M:%S")

        esp_cursor.execute(
            "SELECT COUNT(*) FROM temp_data WHERE sensor_id = %s AND time = %s",
            (sensor, time_date)
        )
        duplicate_count = esp_cursor.fetchone()[0]

        if duplicate_count == 0 and int(temperature) != -127:
            insert_data(temperature, time_date, sensor)
            if not any(sensor_id[0] == sensor for sensor_id in rec):
                rec.append((sensor, 1))
            else:
                for i in range(len(rec)):
                    if rec[i][0] == sensor:
                        rec[i] = (sensor, rec[i][1] + 1)

        rec = sorted(rec, key=lambda x: x[0])

        message = ', '.join(f'sensor {sensor_id}: {count} rec' for sensor_id, count in rec)
        if message != '':
            logger.info(f"Reade {message}, remaining {remain} records from sensors")

    if remain != 0:
        try:
            url = f"http://{ip}/temp?time={entry_time - 100}&limit={remain + 100}"
            response = requests.get(url)
            if response.status_code != 200:
                logger.warning(f"Failed to get data from {ip}. Status code: {response.status_code} 2")
                return False

            curr_time = time.time()
            response = response.json()
            temperatures = response["temperature_data"]
            for record in temperatures:
                sensor = record['sensor_id']
                temperature = record['temp']
                entry_time = record['time']

                if sensor not in lst_request_times:
                    lst_request_times[sensor] = 0

                if entry_time > lst_request_times[sensor]:
                    lst_request_times[sensor] = curr_time - entry_time / 1000

                time_date = datetime.fromtimestamp(curr_time - entry_time / 1000).strftime(
                    "%Y-%m-%d %H:%M:%S")

                esp_cursor.execute(
                    "SELECT COUNT(*) FROM temp_data WHERE sensor_id = %s AND time = %s",
                    (sensor, time_date)
                )
                duplicate_count = esp_cursor.fetchone()[0]

                if duplicate_count == 0 and int(temperature) != -127:
                    insert_data(temperature, time_date, sensor)
                    logger.info("Data inserted successfully")

        except requests.ConnectTimeout:
            logger.error(f"Error requesting data from {ip} (Timeout)")
            for i in range(len(esp_devices)):
                try:
                    while True:
                        url = f"http://{ip}/exit"
                        response = requests.get(url)
                        if response.status_code == 200:
                            logger.info(f"Device {ip} was reset")
                            return True
                        else:
                            logger.error(f"Device not responding. Try to restart device.")
                            esp_devices = [item for item in esp_devices if item[0] != ip]
                            return False
                except:
                    logger.error(f"Device not responding. Try to restart device.")
                    esp_devices = [item for item in esp_devices if item[0] != ip]
            return False


def get_devices():
    global sock,exce
    broadcast_ip = "192.168.0.255"
    udp_port = 4210
    message = f"DISCOVER"

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind((UDP_IP, UDP_PORT))
    sock.sendto(message.encode(), (broadcast_ip, udp_port))
    sock.settimeout(2)

    sock.sendto(message.encode(), (broadcast_ip, udp_port))

    while True:
        try:
            data, addr = sock.recvfrom(1024)
        except TimeoutError:
            break

        if data:
            data = data.decode()
            if "DEVICE" in data:
                match = re.search(r'\[([0-9, ]+)\]', data)
                list_string = match.group(0)
                device = eval(list_string)

                for i in range(0,len(device)):
                    found = any(device[i] in sublist for sublist in esp_devices)
                    if not found:
                        esp_devices.append([addr[0],device[i]])
                        logger.info(f"Added meter device {addr[0]} with id: {device[i]}")

                        exce.append(addr[0])
        else:
            break


def set_params():
    for i in range(0, len(esp_devices)):
        try:
            while True:
                url = f"http://{esp_devices[i][0]}/setinterval?interval={measurement_interval}"
                response = requests.get(url)
                if response.status_code == 200:
                    break
            logger.info(
                f"Time for measurement ({measurement_interval} milliseconds) was set for {esp_devices[i][0]}")
        except Exception:
            logger.error(f"Cant set time for {esp_devices[i][0]}")


def internet_on():
    try:
        s = socket.create_connection(
            ("192.168.0.1", 80))
        if s is not None:
            s.close
        return True
    except OSError:
        pass
    return False


if __name__ == "__main__":
    logger.info('Connecting devices...')
    while internet_on():
        for _ in range(5):
            get_devices()
        break

    for device in esp_devices:
        if internet_on():
            first_request(device[0])
        else:
            time.sleep(1)
    while True:
        if internet_on():
            if time.time() - lst_check > interval / 1000:
                disconnect = False

                grouped_dict = defaultdict(list)
                for key, value in esp_devices:
                    grouped_dict[key].append(value)

                devices = [(key, value) for key, value in grouped_dict.items()]
                for ip, _ in devices:
                    if not disconnect:
                        logger.info(f"Processing device {ip}")
                        get_esp8266_temp(ip, lst_request_times)
                    else:
                        break
                lst_check = time.time()
        else:
            time.sleep(1)

        if time.time() - lst_measure > interval_betweenjson_load / 1000:
            load_config()
            if lst_values != [interval, measurement_interval]:
                set_params()
                logger.info("Configuration params were successfully updated")
                lst_values = [interval, measurement_interval]
            lst_measure = time.time()

        if time.time() - lst_device_upload > 60 or len(esp_devices) == 0:
            logger.info('Pending new devices...')
            for _ in range(10):
                get_devices()

            for device in exce:
                if internet_on():
                    first_request(device)
                    exce.remove(device)
                else:
                    time.sleep(1)

            lst_device_upload = time.time()
        else:
            time.sleep(1)
