from time import sleep
from gpiozero import LED

spot_main = LED(13)
spot_aux = LED (19)
spot_gallery = LED(26)

n = 0
while n < 3:
    sleep(4)
    spot_main.on()
    print("main on")
    sleep(5)
    spot_main.off()
    print("main off")
    sleep(5)
    spot_aux.on()
    print("aux on")
    sleep(5)
    spot_aux.off()
    print("aux off")
    sleep(5)
    spot_gallery.on()
    print("gallery on")
    sleep(5)
    spot_gallery.off()
    print("gallery off")
    n+=1
