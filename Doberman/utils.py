import serial
from subprocess import Popen, PIPE, TimeoutExpired
import importlib
import importlib.machinery
import time
import datetime
import signal
import os.path
import inspect
import re
import logging
import logging.handlers
dtnow = datetime.datetime.now

__all__ = 'FindPlugin SensorOpts Logger number_regex buffer_timer doberman_dir'.split()

heartbeat_timer = 30
buffer_timer = 5
number_regex = r'[\-+]?[0-9]+(?:\.[0-9]+)?(?:[eE][\-+]?[0-9]+)?'
doberman_dir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))

def refreshTTY(db):
    """
    Brute-force matches sensors to ttyUSB assignments by trying
    all possible combinations, and updates the database
    """
    cuts = {'status' : 'online', 'address.tty' : {'$exists' : 1, '$regex' : 'USB'}}
    if db.Count('settings','sensors', cuts):
        print('Some USB sensors are running! Stopping them now')
        running_sensors = db.Distinct('settings','sensors','name', cuts)
        for name in running_sensors:
            db.ProcessCommandStepOne('stop %s' % name)
        time.sleep(heartbeat_timer*1.2)
    else:
        running_sensors = []
    db.updateDatabase('settings','sensors',
            cuts={'address.tty' : {'$exists' : 1, '$regex' : '^0|USB[1-9]?[0-9]'}},
            updates={'$set' : {'address.tty' : '0'}})
    print('Refreshing ttyUSB mapping...')
    proc = Popen('ls /dev/ttyUSB*', shell=True, stdout=PIPE, stderr=PIPE)
    try:
        out, err = proc.communicate(timeout=5)
    except TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
    if not len(out) or len(err):
        raise OSError('Could not check ttyUSB! stdout: %s, stderr %s' % (out.decode(), err.decode()))
    ttyUSBs = out.decode().splitlines()
    cursor = db.readFromDatabase('settings','sensors',
            cuts={'address.tty' : {'$exists' : 1, '$regex' : '^0|USB[1-9]?[0-9]'}})
    sensor_config = {row['name'] : row for row in cursor}
    sensor_names = list(sensor_config.keys())
    sensors = {name: None for name in sensor_names}
    matched = {'sensors' : [], 'ttys' : []}
    for sensor in sensor_names:
        opts = SensorOpts(sensor_config[sensor])
        sensors[sensor] = FindPlugin(sensor, [doberman_dir])(opts)
    dev = serial.Serial()
    for tty in ttyUSBs:
        tty_num = int(re.search('USB([1-9]?[0-9])', tty).group(1))
        print('Checking %s' % tty)
        dev.port = tty
        try:
            dev.open()
        except serial.SerialException as e:
            print('Could not connect to %s: %s' % (tty, e))
            continue
        for name, sensor in sensors.items():
            if name in matched['sensors']:
                continue
            if sensor.isThisMe(dev):
                print('Matched %s to %s' % (tty, name))
                matched['sensors'].append(name)
                matched['ttys'].append(tty)
                db.updateDatabase('settings','sensors', {'name' : name},
                        {'$set' : {'address.tty' : 'USB%i' % tty_num}})
                dev.close()
                break
            #print('Not %s' % name)
            time.sleep(0.5)  # devices are slow
        else:
            print('Could not assign %s!' % tty)
        dev.close()
    if len(matched['sensors']) == len(sensors)-1: # n-1 case
        try:
            name = (set(sensors.keys())-set(matched['sensors'])).pop()
            tty = (set(ttyUSBs) - set(matched['ttys'])).pop()
            print('Matched %s to %s via n-1' % (name, tty))
            db.updateDatabase('settings','sensors', {'name' : name},
                    {'$set' : {'address.tty' : tty.split('tty')[-1]}})
        except:
            pass
    elif len(matched['sensors']) != len(sensors):
        print('Didn\'t find the expected number of sensors!')
        print('Sensors unmatched:')
        l = set(sensors.keys()) - set(matched['sensors'])
        print('\n'.join(l))
        print()
        print('tty ports unmatched:')
        l = set(ttyUSBs) - set(matched['ttys'])
        print('\n'.join(l))
        return False
    #for usb, name in zip(matched['ttys'],matched['sensors']):
    #        db.updateDatabase('settings','sensors', {'name' : name},
    #                {'$set' : {'address.ttyUSB' : int(usb.split('USB')[-1])}})

    db.updateDatabase('settings','current_status', {}, {'$set' : {'tty_update' : dtnow()}})
    for name in running_sensors:
        db.ParseCommand('start %s' % name)
    return True

def FindPlugin(name, path):
    """
    Finds the sensor constructor with the specified name, in the specified paths.
    Will attempt to strip numbers off the end of the name if necessary (ex,
    'iseries1' -> iseries, 'caen_n1470' -> caen_n1470)

    :param name: the name of the sensor you want
    :param path: a list of paths in which to search for the file
    :returns constructor: the constructor of the requested sensor
    """
    strip = False
    if not isinstance(path, (list, tuple)):
        path = [path]
    spec = importlib.machinery.PathFinder.find_spec(name, path)
    if spec is None:
        strip = True
        spec = importlib.machinery.PathFinder.find_spec(name.strip('0123456789'), path)
    if spec is None:
        raise FileNotFoundError('Could not find a sensor named %s in %s' % (name, path))
    try:
        if strip:
            sensor_ctor = getattr(spec.loader.load_module(), name.strip('0123456789'))
        else:
            sensor_ctor = getattr(spec.loader.load_module(), name)
    except AttributeError:
        raise AttributeError('Cound not find constructor for %s!' % name)
    return sensor_ctor

class SignalHandler(object):
    """ Handles signals from the OS
    """
    def __init__(self, logger=None):
        self.run = True
        signal.signal(signal.SIGINT, self.interrupt)
        signal.signal(signal.SIGTERM, self.interrupt)
        self.logger = logger

    def interrupt(self, *args):
        if self.logger is not None:
            self.logger.info('Received signal %i' % args[0])
        self.signal_number = int(args[0])
        self.run = False

class DobermanLogger(logging.Handler):
    """
    Custom logging interface for Doberman. Logs to
    the database (with disk as backup).
    """
    def __init__(self, db, level=logging.INFO):
        logging.Handler.__init__(self)
        self.db = db
        self.db_name = 'logging'
        self.collection_name = 'logs'
        backup_filename = datetime.date.today().isoformat()
        self.backup_logger = logging.handlers.TimedRotatingFileHandler(
                os.path.join(doberman_dir, 'logs', backup_filename + '.log'),
                when='midnight', delay=True)
        self.stream = logging.StreamHandler()
        f = logging.Formatter('%(asctime)s | '
                '%(levelname)s | %(name)s | %(funcName)s | '
                '%(lineno)d | %(message)s')
        self.setFormatter(f)
        self.stream.setFormatter(f)
        self.backup_logger.setFormatter(f)
        self.level = level

    def close(self):
        self.backup_logger.close()
        self.stream.close()
        self.db = None
        return

    def __del__(self):
        self.close()
        return

    def emit(self, record):
        self.stream.emit(record)
        if record.levelno < self.level:
            return
        rec = dict(
                msg         = record.msg,
                level       = record.levelno,
                name        = record.name,
                funcname    = record.funcName,
                lineno      = record.lineno)
        if self.db.insertIntoDatabase(self.db_name, self.collection_name, rec):
            self.backup_logger.emit(record)

def Logger(name, db, loglevel='DEBUG'):
    logger = logging.getLogger(name)
    try:
        lvl = getattr(logging, loglevel)
    except AttributeError:
        lvl = logging.INFO
    logger.setLevel(lvl)
    logger.addHandler(DobermanLogger(db, level=lvl))
    return logger
