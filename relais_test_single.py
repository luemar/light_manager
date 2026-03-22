from time import sleep
from gpiozero import LED

spot_main = LED(19)
spot_aux = LED (13)
spot_gallery = LED(26)

sleep(3)
spot_gallery.on()
print("main on")
sleep(5)
spot_gallery.off()
print("aux off")
