import RPi.GPIO as GPIO
from time import sleep

GPIO.setmode(GPIO.BCM)
GPIO.setup(26, GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(19, GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(13, GPIO.OUT, initial=GPIO.LOW)

print("GPIO set as outputs")
sleep(2)

print("GPIO 26 HIGH")
GPIO.output(26, GPIO.HIGH)
sleep(30)   # measure here

print("GPIO 26 LOW")
GPIO.output(26, GPIO.LOW)
sleep(5)
GPIO.cleanup()

