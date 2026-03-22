from adafruit_extended_bus import ExtendedI2C as I2C
import adafruit_tsl2591
import time

i2c = I2C(1)
sensor = adafruit_tsl2591.TSL2591(i2c)

sensor.gain = adafruit_tsl2591.GAIN_MED  # 25x
sensor.integration_time = adafruit_tsl2591.INTEGRATIONTIME_100MS
sensor.enabled = True
time.sleep(1)
lux = sensor.lux

print(lux)
