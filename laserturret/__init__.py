#from .lasercontrol import LaserControl
#from .steppercontrol import StepperMotor
#from . import lasercontrol, steppercontrol
import configparser
from enum import Enum

config = configparser.ConfigParser()
config.read('laserturret.conf')

class Pins(Enum):
    LASER = config.getint('Laser', 'laser_pin')
    X_CCW_LIMIT = config.getint('GPIO', 'x_ccw_limit_pin')
    X_CW_LIMIT = config.getint('GPIO', 'x_cw_limit_pin')
    Y_CCW_LIMIT = config.getint('GPIO', 'y_ccw_limit_pin')
    Y_CW_LIMIT = config.getint('GPIO', 'y_cw_limit_pin')
    X_DIR = config.getint('Motor', 'x_dir_pin')
    X_STEP = config.getint('Motor', 'x_step_pin')
    X_ENABLE = config.getint('Motor', 'x_enable_pin')
    Y_DIR = config.getint('Motor', 'y_dir_pin')
    Y_STEP = config.getint('Motor', 'y_step_pin')
    Y_ENABLE = config.getint('Motor', 'y_enable_pin')
    MS1 = config.getint('Motor', 'ms1_pin')
    MS2 = config.getint('Motor', 'ms2_pin')
    MS3 = config.getint('Motor', 'ms3_pin')