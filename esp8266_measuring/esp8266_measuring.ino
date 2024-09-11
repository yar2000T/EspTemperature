#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <WiFiUdp.h>
#include <EEPROM.h>
#define SENSORS_PIN D7


OneWire oneWire1(SENSORS_PIN);

DallasTemperature sensors(&oneWire1);

const int numSensors = 3;
const int maxRecords = numSensors * 1000;
const int INTERVAL_ADDRESS_IN_EEPROM = 0;
float temperatures[maxRecords];
unsigned long timestamps[maxRecords];
int ids[maxRecords];
int dataIndex = 0;
unsigned long lastMillis = 0;
int interval = 10000;


unsigned long blink = 0;
int blink_type = 0;

const char* ssid = "YOUR-SSID";
const char* password = "YOUR-PASSWORD";

ESP8266WebServer server(80);
WiFiUDP udp;
const unsigned int udpPort = 4210;
unsigned long lastUdpMillis = 0;

int sensor_ids[numSensors] = {1,2,3};

void writeToEEPROM(int address, int value) {
  EEPROM.put(address, value);
  EEPROM.commit();
}

int readFromEEPROM(int address) {
  int value;
  EEPROM.get(address, value);
  return value;
}

void setup() {
  pinMode(SENSORS_PIN, INPUT_PULLUP);
  pinMode(LED_BUILTIN, OUTPUT);

  sensors.begin();

  Serial.begin(9600);
  EEPROM.begin(512);

  interval = readFromEEPROM(INTERVAL_ADDRESS_IN_EEPROM);
  if (interval <= 0 || interval > 60000) {
    interval = 10000;
    writeToEEPROM(INTERVAL_ADDRESS_IN_EEPROM, interval);
    Serial.println("Interval set to default value: 10000 milliseconds");
  } else {
    Serial.printf("Current interval is %d milliseconds\n", interval);
  }

  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nConnected to WiFi");

  Serial.print("IP Address: ");
  Serial.println(WiFi.localIP());

  udp.begin(udpPort);

  server.on("/setinterval", []() {
    int newInterval = server.arg("interval").toInt();
    if (newInterval > 0 && newInterval <= 60000) {
      interval = newInterval;
      writeToEEPROM(INTERVAL_ADDRESS_IN_EEPROM, interval);
      Serial.printf("Interval updated to %d milliseconds\n", interval);
      server.send(200, "text/html", "<p>Interval set</p>");
    } else {
      server.send(400, "text/html", "<p>Invalid interval</p>");
    }
  });

  server.on("/exit", []() {
    Serial.println("Restarting device...");
    server.send(200, "text/html", "<p>Exiting</p>");
    ESP.restart();
  });

  server.on("/temp", []() {
    String sensor_id = server.arg("sensor_id");
    int limit = server.arg("limit").toInt();
    unsigned long currentMillis = millis();
    unsigned long time_frame = 0;
    bool filterByTime = server.hasArg("time");
    unsigned long requestTime = server.arg("time").toInt() * 1000;

    if (filterByTime) {
      time_frame = currentMillis - requestTime;
    } else {
      time_frame = 0;
    }

    if (limit <= 0) {
      limit = 10;
    }

    String response = "{\"temperature_data\":[";
    int count = 0;
    int totalMatched = 0;

    for (int i = 0; i < maxRecords; i++) {
      bool isWithinTimeFrame = !filterByTime || timestamps[i] >= time_frame;
      bool matchesSensorId = sensor_id.isEmpty() || ids[i] == sensor_id.toInt();

      if (ids[i] != 0 && isWithinTimeFrame && matchesSensorId) {
        totalMatched++;

        if (count < limit) {
          if (count > 0) {
            response += ",";
          }
          response += "{\"temp\":" + String(temperatures[i], 2) + ",\"time\":" + String(currentMillis - timestamps[i]) + ",\"sensor_id\":" + ids[i] + "}";
          count++;
        }
      }
    }

    int remainCount = totalMatched - count;
    response += "],\"remain_cnt\":" + String(remainCount) + "}";
    server.send(200, "application/json", response);
  });

  Serial.println("Server started");
  server.begin();
}

void loop() {
  server.handleClient();

  if (millis() - blink >= 100) {
    blink = millis();

    if (blink_type == 1) {
      digitalWrite(LED_BUILTIN, HIGH);
      blink_type = 0;
    }else{
      digitalWrite(LED_BUILTIN, LOW);
      blink_type = 1;
    }
  }

  if (millis() - lastMillis >= interval) {
      lastMillis = millis();
  
      for (int i = 0; i < numSensors; i++) {
          sensors.requestTemperatures();
          float temperature = sensors.getTempCByIndex(i);

          if (dataIndex > numSensors * 2) {
              float lastTemperature = temperatures[(dataIndex - numSensors + maxRecords) % maxRecords];
              float secondLastTemperature = temperatures[(dataIndex - (numSensors * 2) + maxRecords) % maxRecords];

              float diffLast = abs(temperature - lastTemperature);
              float diffSecondLast = abs(temperature - secondLastTemperature);

              if (diffLast <= 0.2 && diffSecondLast <= 0.2) {
                  timestamps[(dataIndex - 3 + maxRecords) % maxRecords] = millis();
              } else {
                  temperatures[dataIndex] = temperature;
                  timestamps[dataIndex] = millis();
                  ids[dataIndex] = sensor_ids[i];
                  dataIndex = (dataIndex + 1) % maxRecords;
              }
          } else {
              temperatures[dataIndex] = temperature;
              timestamps[dataIndex] = millis();
              ids[dataIndex] = sensor_ids[i];
              dataIndex = (dataIndex + 1) % maxRecords;
          }
      }
  }


  if (millis() - lastUdpMillis > 1000) {
    int packetSize = udp.parsePacket();
    if (packetSize) {
      char packetBuffer[255];
      int len = udp.read(packetBuffer, sizeof(packetBuffer) - 1);
      packetBuffer[len] = '\0';
      if (len > 0) {
        String packetString = String(packetBuffer);

        if (packetString.indexOf("DISCOVER") >= 0) {
          if (packetString.indexOf(WiFi.localIP().toString()) < 0) { 
            IPAddress remoteIp = udp.remoteIP();
            Serial.print("Device with IP: ");
            Serial.print(remoteIp);
            Serial.print(" is attempting to connect...");

            udp.beginPacket(remoteIp, udpPort);
            String message = "'DEVICE' ," + String(numSensors) + ", [";
            for (int i = 0; i < numSensors; i++) {
              message += sensor_ids[i];
              if (i < numSensors - 1)  message += ", ";
            }
            message += "]";
            udp.print(message);
            udp.endPacket();
            Serial.println("Response packet sent");
          }
        }
      } else {
        Serial.println("Error reading UDP packet");
      }
    }
    lastUdpMillis = millis();
  }
}
