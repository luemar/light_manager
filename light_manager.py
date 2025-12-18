#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time, json, datetime, random, logging, sys, os, warnings
from gpiozero import LED
from adafruit_extended_bus import ExtendedI2C as I2C
import adafruit_tsl2561

# -------------------- CONFIG --------------------
CONFIG_FILE = "/home/pi/light_schedule.json"
STATE_FILE  = "/home/pi/light_state.json"
LOG_FILE    = "/home/pi/light_manager.log"

os.environ["GPIOZERO_PIN_FACTORY"] = "rpigpio"
warnings.filterwarnings("ignore")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(LOG_FILE, mode="a")]
)
logging.info(">>> light_manager.py STARTED <<<")

# -------------------- GPIO --------------------
SPOTS = {
    "main":    LED(13),
    "aux":     LED(19),
    "gallery": LED(26),
}

STATUS_LED = LED(5)
STATUS_LED.on()

for s in SPOTS.values():
    s.off()

# -------------------- SENSOR --------------------
i2c = I2C(3)
sensor = adafruit_tsl2561.TSL2561(i2c)
sensor.enabled = True
time.sleep(1)

# -------------------- HELPERS --------------------
def read_config():
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Failed to read config: {e}")
        return {}


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_state(state):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        logging.error(f"Failed to save state: {e}")


def get_lux():
    for _ in range(3):
        try:
            lux = sensor.lux
            if lux is None or lux < 0:
                raise ValueError
            return lux
        except Exception:
            time.sleep(0.5)
    logging.warning("Lux read failed — assuming bright")
    return 9999


def parse_time(tstr):
    """Parse HH:MM string to datetime.time object"""
    h, m = map(int, tstr.split(":"))
    return datetime.time(h, m)


def time_to_minutes(t):
    """Convert time object to minutes since midnight"""
    return t.hour * 60 + t.minute


def is_between(now, start_str, end_str):
    """Check if current time is between start and end (with second precision)"""
    start = parse_time(start_str)
    end   = parse_time(end_str)
    t = now.time()
    
    # Convert to minutes for cleaner comparison
    now_min = time_to_minutes(t)
    start_min = time_to_minutes(start)
    end_min = time_to_minutes(end)
    
    if start_min <= end_min:
        return start_min <= now_min < end_min
    else:
        # Handle midnight crossing
        return now_min >= start_min or now_min < end_min


def time_with_offset(base, offset):
    """Apply offset in seconds to a time string"""
    t = parse_time(base)
    dt = datetime.datetime.combine(datetime.date.today(), t)
    return (dt + datetime.timedelta(seconds=offset)).time()


def format_time(t):
    """Format time object as HH:MM string"""
    return t.strftime("%H:%M")

# -------------------- STATE --------------------
state = load_state()   # persisted desired state
last_day = None
rnd_on = 0
rnd_off = 0

# -------------------- MAIN LOOP --------------------
try:
    while True:
        now = datetime.datetime.now()
        cfg = read_config()

        check_interval = cfg.get("check_interval", 60)
        threshold      = cfg.get("threshold", 120)
        hysteresis     = cfg.get("hysteresis", 15)

        # ---- Daily random offsets (reset at midnight) ----
        if last_day != now.day:
            # Uncomment these for production use:
            # rnd_on  = random.randint(60, 180)
            # rnd_off = random.randint(180, 300)
            
            # For testing, keep at 0:
            rnd_on = 0
            rnd_off = 0
            
            last_day = now.day
            logging.info(f"New daily offsets: on={rnd_on}s off={rnd_off}s")

        lux = get_lux()
        logging.info(f"Brightness: {lux:.1f} lux")

        # ---- Compute desired state for each light ----
        def should_be_on(name):
            """Determine if a light should be ON based on schedule and sensors"""
            prev_state = state.get(name, False)

            # Gallery and Aux: Pure schedule-based control
            if name in ("gallery", "aux"):
                on_k, off_k = f"{name}_on", f"{name}_off"
                if on_k in cfg and off_k in cfg:
                    # Apply random offsets to scheduled times
                    on_t  = time_with_offset(cfg[on_k],  rnd_on)
                    off_t = time_with_offset(cfg[off_k], rnd_off)
                    
                    # Check if current time is within the ON window
                    result = is_between(now, format_time(on_t), format_time(off_t))
                    return result
                return False

            # Main: Brightness-based with manual override
            if name == "main":
                # Check for manual override (main_off time reached)
                if "main_off" in cfg:
                    off_time = parse_time(cfg["main_off"])
                    if now.time() >= off_time:
                        return False
                
                # Brightness-based control with hysteresis
                if prev_state:
                    # Currently ON: turn off only if bright enough
                    return lux < threshold + hysteresis
                else:
                    # Currently OFF: turn on only if dark enough
                    return lux < threshold - hysteresis

            return False

        # ---- Apply state changes with edge detection ----
        for name, led in SPOTS.items():
            want = should_be_on(name)
            prev = state.get(name)

            # Log state transitions
            if prev is None:
                logging.info(f"{name} init: desired={want}")
            elif prev != want:
                logging.info(f"{name} transition: {prev} -> {want}")

            # Synchronize LED with desired state
            if want:
                if not led.is_lit:
                    led.on()
                    logging.info(f"{name} turned ON")
            else:
                if led.is_lit:
                    led.off()
                    logging.info(f"{name} turned OFF")

            # Update state
            state[name] = want

        save_state(state)
        time.sleep(check_interval)

except KeyboardInterrupt:
    logging.info("Light manager stopped manually")
    for s in SPOTS.values():
        s.off()

