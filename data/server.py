from flask import Flask, render_template, request, redirect, url_for
from dotenv import load_dotenv
import mysql.connector
from os import getenv,path
import logging
import socket
import json

local_ip = socket.gethostbyname(socket.gethostname())

app = Flask(__name__)
logger = logging.getLogger(__name__)

log = logging.getLogger('werkzeug')
log.disabled = True
del log

print(f"Running on {local_ip}")

p = path.abspath('..') + "\\.env"

load_dotenv(p)


DATABASE_HOST: str = getenv('DATABASE_HOST')
DATABASE_PORT: int = int(getenv('DATABASE_PORT'))
DATABASE_USER: str = getenv('DATABASE_USER')
DATABASE_PASSWORD: str = getenv('DATABASE_PASSWORD')
DATABASE: str = getenv('DATABASE')

def set_format():
    formatter = logging.Formatter('%(asctime)s - %(message)s')

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    logger.addHandler(console_handler)


set_format()


def get_database():
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
    except mysql.connector.Error as e:
        logger.error(f"Error connecting to MySQL database: {e}")
        exit()


def load_config():
    with open('config.json', 'r') as config_file:
        return json.load(config_file)['config']


def save_config(config):
    with open('config.json', 'w') as config_file:
        json.dump({'config': config}, config_file, indent=4)


@app.route('/', methods=['GET', 'POST'])
def dashboard():
    get_database()
    config_params = load_config()

    if request.method == 'POST':
        if 'add_sensor' in request.form:
            id = request.form['id']
            location = request.form['location']

            esp_cursor.execute(
                "INSERT INTO sensorId_list VALUES (%s, %s)",
                (id, location)
            )
            esp_db.commit()
            return redirect(url_for('dashboard'))

        if 'clear_logs' in request.form:
            open("data/app.log", 'w').close()
            return redirect(url_for('dashboard'))

        elif 'delete_sensor' in request.form:
            id = request.form['user_id']
            esp_cursor.execute(f"DELETE FROM sensorId_list WHERE id = {id}")
            esp_db.commit()
            esp_cursor.execute(f"DELETE FROM temp_data WHERE id = {id}")
            esp_db.commit()
            return redirect(url_for('dashboard'))

        elif 'update_config' in request.form:
            for key in config_params.keys():
                config_params[key] = int(request.form[key])
            save_config(config_params)
            return redirect(url_for('dashboard'))

        elif 'edit_data' in request.form:
            id = request.form['edit_sensor']
            location = request.form['edit_location']

            esp_cursor.execute(f"UPDATE sensorId_list SET location = '{location}' WHERE id = {int(id)};")
            esp_db.commit()

            return redirect(url_for('dashboard'))

        elif 'clear_db' in request.form:
            esp_cursor.execute(f"DELETE FROM temp_data;")
            esp_db.commit()

    esp_cursor.execute("SELECT id, location FROM sensorId_list")
    id_location = esp_cursor.fetchall()

    temp_list = [str(row[0]) for row in id_location]

    if temp_list:
        formatted_temp_list = ','.join(temp_list)

        query = f"""
        SELECT sensor_id, temp
        FROM temp_data
        WHERE (sensor_id, time) IN (
            SELECT sensor_id, MAX(time)
            FROM temp_data
            WHERE sensor_id IN ({formatted_temp_list})
            GROUP BY sensor_id
        )
        """

        esp_cursor.execute(query)
        data1 = esp_cursor.fetchall()
    else:
        data1 = []

    for i in range(0, len(data1)):
        data1[i] = data1[i] + (id_location[i][1],)

    data = open("app.log", 'r').readlines()
    return render_template('dev.html', sensors=id_location, logs=data, sensor_list=data1, config_params=config_params)


app.run(host='0.0.0.0')
