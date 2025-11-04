import time, json, datetime, random, logging, sys
from gpiozero import LED
from adafruit_extended_bus import ExtendedI2C as I2C
import adafruit_tsl2561
import os, warnings
os.environ["GPIOZERO_PIN_FACTORY"] = "rpigpio"  # use clean GPIO backend

LOG_FILE = "/home/pi/light_manager.log"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", handlers= \
                    [logging.StreamHandler(sys.stdout), \
                     logging.FileHandler(LOG_FILE, mode='a')])
logging.info(">>> light_manager.py STARTED <<<")

warnings.filterwarnings("ignore") #silence non-critical library warnings

CONFIG_FILE = "/home/pi/light_schedule.json"
l_mgt_on = LED(5)

SPOTS = {
    "main": LED(13),
    "aux": LED(19),
    "gallery": LED(26)
}

for s in SPOTS.values():
    s.off()
spot_main_off = False

# Setup sensor
i2c = I2C(3)
sensor = adafruit_tsl2561.TSL2561(i2c)
sensor.enabled = True
time.sleep(1)

def read_config():
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Failed to read config: {e}")
        return {}

def get_lux():
    for _ in range(3): #try up to 3 times
        try:
            lux = sensor.lux
            if lux is None or lux < 0:
                raise ValueError("invalid lux")
            return lux
        except Exception:
            time.sleep(0.5)
    logging.warning("Repeated lux read failures, reinitializing sensor.")
    try:
        sensor.enabled = False
        time.sleep(0.5)
        sensor.enabled = True
    except Exception as e:
        logging.error(f"Sensor reinit failed: {e}")
    return 9999

def parse_time(tstr):
    h, m = map(int, tstr.split(":"))
    return datetime.time(h, m)

def due(now, target):
    return now.hour == target.hour and now.minute == target.minute

def control_spot(name, action):
    spot = SPOTS[name]
    if action == "on" and not spot.is_lit:
        spot.on()
        logging.info(f"{name} turned ON")
    elif action == "off" and spot.is_lit:
        spot.off()
        logging.info(f"{name} turned OFF")

def is_between(now, start_str, end_str):
    """Return True if current time is between start and end times."""
    start = parse_time(start_str)
    end = parse_time(end_str)
    now_t = now.time()
    if start <= end:
        return start <= now_t < end
    else:
        # handles intervals that cross midnight
        return now_t >= start or now_t < end

# Helper for comparing times + random offsets
def time_with_offset(base_time, offset):
    t = parse_time(base_time)
    dt = datetime.datetime.combine(datetime.date.today(), t) + datetime.timedelta(seconds=offset)
    return dt.time()


# --- Initial states ---
logging.info("Light manager started")
l_mgt_on.on()
last_minute = None
last_day = None
first_run = True

# Initialize daily random offsets
random_offset_1 = random.randint(60, 180)
random_offset_2 = random.randint(180, 300)
logging.info(f"New daily random_offset_1={random_offset_1}s,\
               random_offset_2={random_offset_2}s")
#main loop
try:
    while True:
        now = datetime.datetime.now()
        cfg = read_config()
        threshold = cfg.get("threshold", 110)
        check_interval = cfg.get("check_interval", 60)

        # --- Reset random offsets at midnight ---
        if last_day != now.day:
            random_offset_1 = random.randint(60, 180)
            random_offset_2 = random.randint(180, 300)
            last_day = now.day
            logging.info(f"New daily random_offset_1={random_offset_1}s,\
                         random_offset_2={random_offset_2}s")

        # --- Brightness-based control for spot_main ---
        lux = get_lux()
        logging.info(f"Brightness: {lux:.1f} lux (main.is_lit={SPOTS['main'].is_lit})")
        HYSTERESIS = 20
        if not spot_main_off:
            if lux < threshold - HYSTERESIS and not SPOTS["main"].is_lit:
                SPOTS["main"].on()
                logging.info(f"spot_main ON (lux < {threshold - HYSTERESIS})")
            elif lux >= threshold + HYSTERESIS and SPOTS["main"].is_lit:
                SPOTS["main"].off()
                logging.info(f"spot_main OFF (lux >= {threshold + HYSTERESIS})")

        # --- Time-based control (check once per minute) ---
        if now.minute != last_minute:
            last_minute = now.minute

            # Normal scheduled ON/OFFtimes with random_offsets
            if now.hour == 0 and now.minute == 0:
                spot_main_off = False

            if "main_off" in cfg and due(now, parse_time(cfg["main_off"])):
                control_spot("main", "off")
                spot_main_off = True

            if "gallery_on" in cfg and due(now, time_with_offset(cfg["gallery_on"], random_offset_1)):
                control_spot("gallery", "on")
            if "gallery_off" in cfg and due(now, time_with_offset(cfg["gallery_off"], random_offset_2)):
                control_spot("gallery", "off")

            if "aux_on" in cfg and due(now, time_with_offset(cfg["aux_on"], random_offset_1)):
                control_spot("aux", "on")
            if "aux_off" in cfg and due(now, time_with_offset(cfg["aux_off"], random_offset_2)):
                control_spot("aux", "off")

             # --- Catch-up logic: ensure lights are ON if current time is within ON/OFF window ---
            if "gallery_on" in cfg and "gallery_off" in cfg:
                if is_between(now, cfg["gallery_on"], cfg["gallery_off"]) and not SPOTS["gallery"].is_lit:
                    logging.info("Catch-up: gallery ON (booted after scheduled ON time)")
                    control_spot("gallery", "on")

            if "aux_on" in cfg and "aux_off" in cfg:
                if is_between(now, cfg["aux_on"], cfg["aux_off"]) and not SPOTS["aux"].is_lit:
                    logging.info("Catch-up: aux ON (booted after scheduled ON time)")
                    control_spot("aux", "on")

        time.sleep(check_interval)

except KeyboardInterrupt:
    logging.info("Light manager stopped manually")
    for spot in SPOTS.values():
        spot.off()

