from subprocess import Popen, PIPE, TimeoutExpired
import importlib
import importlib.machinery
import time
import datetime
import signal
import os.path
import os
import inspect
import re
import logging
import logging.handlers
import serial
import threading

dtnow = datetime.datetime.now

__all__ = 'find_plugin heartbeat_timer number_regex doberman_dir get_logger'.split()

heartbeat_timer = 30
number_regex = r'[\-+]?[0-9]+(?:\.[0-9]+)?(?:[eE][\-+]?[0-9]+)?'
doberman_dir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))


def refresh_tty(db):
    """
    Brute-force matches sensors to ttyUSB assignments by trying
    all possible combinations, and updates the database
    """
    cuts = {'status': 'online', 'address.tty': {'$exists': 1, '$regex': 'USB'}}
    if db.count('settings', 'sensors', cuts):
        print('Some USB sensors are running! Stopping them now')
        running_sensors = db.distinct('settings', 'sensors', 'name', cuts)
        for name in running_sensors:
            db.ProcessCommandStepOne('stop %s' % name)
        time.sleep(heartbeat_timer * 1.2)
    else:
        running_sensors = []
    db.update_db('settings', 'sensors',
                 cuts={'address.tty': {'$exists': 1, '$regex': '^0|USB[1-9]?[0-9]'}},
                 updates={'$set': {'address.tty': '0'}})
    print('Refreshing ttyUSB mapping...')
    proc = Popen('ls /dev/ttyUSB*', shell=True, stdout=PIPE, stderr=PIPE)
    try:
        out, err = proc.communicate(timeout=5)
    except TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
    if not out or err:
        raise OSError('Could not check ttyUSB! stdout: %s, stderr %s' % (out.decode(), err.decode()))
    tty_usbs = out.decode().splitlines()
    cursor = db.read_from_db('settings', 'sensors',
                             cuts={'address.tty': {'$exists': 1, '$regex': '^0|USB[1-9]?[0-9]'}})
    sensor_config = {row['name']: row for row in cursor}
    sensor_names = list(sensor_config.keys())
    sensors = {name: None for name in sensor_names}
    matched = {'sensors': [], 'ttys': []}
    for sensor in sensor_names:
        opts = SensorOpts(sensor_config[sensor])
        sensors[sensor] = find_plugin(sensor, [doberman_dir])(opts)
    dev = serial.Serial()
    for tty in tty_usbs:
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
            if sensor.is_this_me(dev):
                print('Matched %s to %s' % (tty, name))
                matched['sensors'].append(name)
                matched['ttys'].append(tty)
                db.update_db('settings', 'sensors', {'name': name},
                             {'$set': {'address.tty': 'USB%i' % tty_num}})
                dev.close()
                break
            # print('Not %s' % name)
            time.sleep(0.5)  # devices are slow
        else:
            print('Could not assign %s!' % tty)
        dev.close()
    if len(matched['sensors']) == len(sensors) - 1:  # n-1 case
        try:
            name = (set(sensors.keys()) - set(matched['sensors'])).pop()
            tty = (set(tty_usbs) - set(matched['ttys'])).pop()
            print('Matched %s to %s via n-1' % (name, tty))
            db.update_db('settings', 'sensors', {'name': name},
                         {'$set': {'address.tty': tty.split('tty')[-1]}})
        except:
            pass
    elif len(matched['sensors']) != len(sensors):
        print('Didn\'t find the expected number of sensors!')
        print('Sensors unmatched:')
        l = set(sensors.keys()) - set(matched['sensors'])
        print('\n'.join(l))
        print()
        print('tty ports unmatched:')
        l = set(tty_usbs) - set(matched['ttys'])
        print('\n'.join(l))
        return False
    # for usb, name in zip(matched['ttys'],matched['sensors']):
    #        db.updateDatabase('settings','sensors', {'name' : name},
    #                {'$set' : {'address.ttyUSB' : int(usb.split('USB')[-1])}})

    db.update_db('settings', 'current_status', {}, {'$set': {'tty_update': dtnow()}})
    for name in running_sensors:
        db.ParseCommand('start %s' % name)
    return True


def find_plugin(name, path):
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

    def __init__(self, logger=None, event=None):
        self.run = True
        signal.signal(signal.SIGINT, self.interrupt)
        signal.signal(signal.SIGTERM, self.interrupt)
        self.logger = logger
        self.event = event

    def interrupt(self, *args):
        if self.logger is not None:
            self.logger.info('Received signal %i' % args[0])
        self.signal_number = int(args[0])
        self.run = False
        if self.event is not None:
            self.event.set()


class DobermanLogger(logging.Handler):
    """
    Custom logger for Doberman. DEBUG goes to disk in one file, INFO and higher also goes to disk in another file,
    WARNING and higher go to the database. The DEBUG files will get purged regularly because they'll be quite bulky,
    while "important" info will remain in the long-term logfiles. Logfiles will get rotated daily with folder
    structure YYYY/MM.DD and unique named files.
    """
    def __init__(self, db, name):
        logging.Handler.__init__(self)
        self.mutex = threading.Lock()
        self.db = db
        self.name = name
        self.experiment = db.experiment_name
        self.db_name = 'logging'
        self.collection_name = 'logs'
        self.today = datetime.date.today()
        self.open_files(self.today)
        self.flush_cycle = 0

    def rotate(self, when):
        for f in cls.files.values():
            if f is not None:
                f.close()
        self.today = datetime.date.today()
        self.open_files(when)

    def open_files(self, when):
        self.files = {'DEBUG': open(os.path.join(self.logdir(when), self.filename(when, 'DEBUG')), 'a'),
                'INFO': open(os.path.join(self.logdir(when), self.filename(when)), 'a')}
        for k in 'WARNING ERROR FATAL'.split():
            # copy for INFO and higher
            self.files[k] = self.files['INFO']

    def filename(self, when, level=None):
        lvl = '' if level is None else f'{level}_'
        return f'{lvl}{self.name}.log'

    def logdir(self, when):
        """
        Returns a directory where you can put the day's logs. Creates the directories if they dont exist
        """
        # TODO have the path be configurable somehow?
        p = f'/global/logs/{self.experiment}/{when.year}/{when.month:02d}.{when.day:02d}'
        os.makedirs(p, exist_ok=True)
        return p

    def emit(self, record):
        msg_datetime = datetime.datetime.fromtimestamp(record.created)
        msg_date = datetime.date(msg_datetime.year, msg_datetime.month, msg_datetime.day)
        m = self.format_message(msg_datetime, record.levelname, record.funcName, record.lineno, record.getMessage())
        with self.mutex:
            # we wrap anything hitting files or stdout with a mutex because logging happens from
            # multiple threads, and files aren't thread-safe
            if msg_date != self.today:
                # it's a brand new day, and the sun is high...
                self.rotate(msg_date)
            print(m)
            self.files['DEBUG'].write(m + '\n') # everything goes to debug
            if record.levelno != logging.DEBUG:
                self.files.get(str(record.levelname).upper(), self.files['INFO']).write(m + '\n')
            self.flush_cycle += 1
            if self.flush_cycle > 10: # TODO make config value?
                # if we don't regularly flush the buffers, messages will sit around in memory rather than actually
                # get pushed to disk, and we don't want this. If we do it too frequently it's slow
                for f in self.files.values():
                    f.flush()
                self.flush_cycle = 0
        if record.levelno > logging.INFO:
            rec = dict(
                msg=record.getMessage(),
                level=record.levelno,
                name=record.name,
                funcname=record.funcName,
                lineno=record.lineno,
                date=msg_datetime,
                )
            self.db.insert_into_db(self.db_name, self.collection_name, rec)

    def format_message(self, when, level, func_name, lineno, msg):
        return f'{when.isoformat(sep=" ")} | {str(level).upper()} | {self.name} | {func_name} | {lineno} | {msg}'


def get_logger(name, db):
    logger = logging.getLogger(name)
    logger.addHandler(DobermanLogger(db, name))
    logger.setLevel(logging.DEBUG)
<<<<<<< HEAD
=======
=======
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

    def __del__(self):
        self.close()

    def emit(self, record):
        self.stream.emit(record)
        if record.levelno < self.level or record.levelno <= logging.DEBUG:
            return
        rec = dict(
            msg=record.msg,
            level=record.levelno,
            name=record.name,
            funcname=record.funcName,
            lineno=record.lineno)
        if self.db.insert_into_db(self.db_name, self.collection_name, rec):
            self.backup_logger.emit(record)


def logger(name, db, loglevel='DEBUG'):
    logger = logging.getLogger(name)
    try:
        lvl = getattr(logging, loglevel)
    except AttributeError:
        lvl = logging.INFO
    logger.setLevel(lvl)
    logger.addHandler(DobermanLogger(db, level=lvl))
>>>>>>> f0454c9472bbbe22bc8153e48d9b8c6b2fa07413
>>>>>>> 4e02daf4d066dbccc64b19fc4e039bca80095440
    return logger
