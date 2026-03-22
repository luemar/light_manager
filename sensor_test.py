import time
import board
import busio
import adafruit_tsl2591
from adafruit_extended_bus import ExtendedI2C as I2C
i2c = I2C(3)  # Use bus 3

sensor = adafruit_tsl2591.TSL2591(i2c)

#sensor.enabled = True
time.sleep(1)  # Give it time to take a reading

print('Lux: {}'.format(sensor.lux))
#print('Broadband: {}'.format(sensor.broadband))
print('Visible: {}'.format(sensor.visible))
print('Infrared: {}'.format(sensor.infrared))
#print('Luminosity: {}'.format(sensor.luminosity))
print('Full spectrum {}'.format(sensor.full_spectrum))
