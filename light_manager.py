#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time, json, datetime, random, logging, sys, os, warnings
from gpiozero import LED
from adafruit_extended_bus import ExtendedI2C as I2C
import adafruit_tsl2591

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

# Manual LED state tracking (more reliable than led.is_lit)
led_states = {name: False for name in SPOTS}

STATUS_LED = LED(5)
STATUS_LED.on()

for s in SPOTS.values():
    s.off()

# -------------------- SENSOR --------------------
i2c = I2C(1)
sensor = None
for attempt in range(10):
    try:
        sensor = adafruit_tsl2591.TSL2591(i2c)
        sensor.gain = adafruit_tsl2591.GAIN_MED  # 25x
        sensor.integration_time = adafruit_tsl2591.INTEGRATIONTIME_100MS
        sensor.enabled = True
        time.sleep(1)

        #test read
        lux = sensor.lux
        logging.info("Sensor initialized successfully")
        break

    except Exception as e:
        logging.warning(f"Sensor failed attempt{attempt+1}/10: {e}")

if sensor is None:
    logging.error("Sensor failed to initialize after retries")
    sys.exit(1)
# Track consecutive sensor failures
consecutive_failures = 0
last_good_lux = None

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
    global consecutive_failures, last_good_lux, sensor, i2c

    # Try normal readfirst
    for _ in range(3):
        try:
            lux = sensor.lux
            if lux is not None and lux >= 0:
                consecutive_failures = 0
                last_good_lux = lux
                return lux
        except Exception:
            time.sleep(0.5)

    # If we get here, all retries failed
    consecutive_failures += 1
    
    # Try reinit only every 10 failures (not every minute)
    if consecutive_failures % 10 == 1:
        logging.warning("Lux read failed - attempting sensor reinit")
        try:
            sensor.enabled = False
            time.sleep(1)
            sensor.enabled = True
            time.sleep(1)
            lux = sensor.lux
            if lux is not None and lux >= 0:
                logging.info("Sensor reinitialized successfully")
                consecutive_failures = 0
                last_good_lux = lux
                return lux
        except Exception as e:
            logging.error(f"Sensor reinit failed: {e}")

    # After many failures, try recreating the sensor object
    if consecutive_failures == 30:
        logging.warning("30 consecutive failures - attempting full sensor reset")
        try:
            sensor = adafruit_tsl2591.TSL2591(i2c)
            sensor.enabled = True
            time.sleep(1)
            lux = sensor.lux
            if lux is not None and lux >= 0:
                logging.info("Full sensor reset successful")
                consecutive_failures = 0
                last_good_lux = lux
                return lux
        except Exception as e:
            logging.error(f"Full sensor reset failed: {e}")

    # Use last known good value if available and recent
    if last_good_lux is not None and consecutive_failures < 60:
        if consecutive_failures == 1:
            logging.warning(f"Using last known lux value: {last_good_lux:.1f}")
        return last_good_lux
    
    # Complete failure - assume bright
    if consecutive_failures % 60 == 0:  # Log every hour
        logging.error(f"Sensor failed for {consecutive_failures} minutes - assuming bright")
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
spot_main_off = False  # Track if main_off time has been reached

# -------------------- MAIN LOOP --------------------
try:
    while True:
        now = datetime.datetime.now()
        cfg = read_config()

        check_interval = cfg.get("check_interval", 180)
        threshold      = cfg.get("threshold", 50)
        hysteresis     = cfg.get("hysteresis", 15)

        # ---- Daily random offsets (reset at midnight) ----
        if last_day != now.day:
            # Uncomment these for production use:
            # rnd_on  = random.randint(60, 180)
            # rnd_off = random.randint(180, 300)
            
            # For testing, keep at 0:
            rnd_on = 0
            rnd_off = 0
            
            # Reset main_off flag at midnight
            spot_main_off = False

            last_day = now.day
            logging.info(f"New daily offsets: on={rnd_on}s off={rnd_off}s")

        lux = get_lux()
        logging.info(f"Brightness: {lux:.1f} lux")

        # ---- Compute desired state for each light ----
        def should_be_on(name):
            """Determine if a light should be ON based on schedule and sensors"""
            global spot_main_off  # CRITICAL: Must declare global to modify it
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
                # RULE: Never turn ON between midnight (00:00) and noon (12:00)
                if 0 <= now.hour < 15:
                    return False
                # Check for manual override (main_off time reached)
                if "main_off" in cfg and not spot_main_off:
                    off_time = parse_time(cfg["main_off"])
                    if now.time() >= off_time:
                        spot_main_off = True
                        return False
                
                # If override is active, stay off
                if spot_main_off:
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

            # Control LED using manual state tracking (more reliable than led.is_lit)
            if want:
                if not led_states[name]:  # Check our manual tracking
                    led.on()
                    led_states[name] = True
                    logging.info(f"{name} turned ON")
            else:
                if led_states[name]:  # Check our manual tracking
                    led.off()
                    led_states[name] = False
                    logging.info(f"{name} turned OFF")

            # Update state
            state[name] = want

        save_state(state)
        time.sleep(check_interval)

except KeyboardInterrupt:
    logging.info("Light manager stopped manually")
    for s in SPOTS.values():
        s.off()
