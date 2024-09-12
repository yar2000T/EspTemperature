EspTemperature.md
------------------
![](https://github.com/yar2000T/EspTemperature/blob/main/logo.png?raw=True)

# Installation

## pip
Install packages using pip `pip install -r requirements.txt`
## Docker
To install **docker machine** you can follow this step-by-step [guide](https://www.youtube.com/watch?v=ZyBBv1JmnWQ&ab_channel=CodeBear "guide")


#### Mysql
You can install your MySQL database directly on your OS but, I recommend installing it in docker-machine. Here is [tutorial](https://www.datacamp.com/tutorial/set-up-and-configure-mysql-in-docker "tutorial")


#### Mysql database
You need to create a database named **esp_data**. Then you can use this script to create a table:

``CREATE TABLE 'temp_data' (
  'id' int NOT NULL AUTO_INCREMENT,
  'temp' float NOT NULL,
  'time' timestamp NOT NULL,
  'sensor_id' int NOT NULL,
  PRIMARY KEY ('id')
) ENGINE=InnoDB AUTO_INCREMENT=0 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;``


### Esp8266
To use this project you need an esp8266 with wifi support. You need only
1. port D7, 3v, GND.
2. a temperature sensor like 0750C3
3. installed esp8266 plugin (fast [tutorial]( https://www.youtube.com/watch?v=OC9wYhv6juM&ab_channel=RuiSantos "tutorial"))


#### Connecting esp8266 board
Here is a photo of the schema that is used:


![](https://github.com/yar2000T/EspTemperature/blob/main/schema.png?raw=true)


## Modify script plan

- [x] Write cpp for board
- [x] Write python script
- [ ] Create unit tests
- [x] More optimized code

### End
