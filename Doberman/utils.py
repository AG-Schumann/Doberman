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
from pytz import utc
import threading
import hashlib
from math import floor, log10
import itertools


def dtnow():
    return datetime.datetime.now(tz=utc) # no timezone nonsense, now

__all__ = 'dtnow find_plugin number_regex get_logger make_hash sensible_sig_figs SortedBuffer'.split()

number_regex = r'[\-+]?[0-9]+(?:\.[0-9]+)?(?:[eE][\-+]?[0-9]+)?'
doberman_dir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))

def find_plugin(name, path):
    """
    Finds the device constructor with the specified name, in the specified paths.
    Will attempt to strip numbers off the end of the name if necessary (ex,
    'iseries1' -> iseries, 'caen_n1470' -> caen_n1470)

    :param name: the name of the device you want
    :param path: a list of paths in which to search for the file
    :returns constructor: the constructor of the requested device
    """
    strip = False
    if not isinstance(path, (list, tuple)):
        path = [path]
    spec = importlib.machinery.PathFinder.find_spec(name, path)
    if spec is None:
        strip = True
        spec = importlib.machinery.PathFinder.find_spec(name.strip('0123456789'), path)
    if spec is None:
        raise FileNotFoundError('Could not find a device named %s in %s' % (name, path))
    try:
        if strip:
            device_ctor = getattr(spec.loader.load_module(), name.strip('0123456789'))
        else:
            device_ctor = getattr(spec.loader.load_module(), name)
    except AttributeError:
        raise AttributeError('Cound not find constructor for %s!' % name)
    return device_ctor


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
        self.f = None
        self.open_files(self.today)
        self.flush_cycle = 0

    def rotate(self, when):
        if self.f is not None:
            self.f.close()
        self.today = datetime.date.today()
        self.open_files(when)

    def open_files(self, when):
        self.f = open(self.full_file_path(when), 'a')

    def full_file_path(self, when):
        return os.path.join(self.logdir(when), self.filename(when))

    def filename(self, when):
        return f'{self.name}.log'

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
            self.f.write(m + '\n')
            self.flush_cycle += 1
            if self.flush_cycle > 10: # TODO make config value?
                # if we don't regularly flush the buffers, messages will sit around in memory rather than actually
                # get pushed to disk, and we don't want this. If we do it too frequently it's slow
                self.f.flush()
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
            self.db.insert_into_db(self.collection_name, rec)

    def format_message(self, when, level, func_name, lineno, msg):
        return f'{when.isoformat(sep=" ")} | {str(level).upper()} | {self.name} | {func_name} | {lineno} | {msg}'


def get_logger(name, db):
    logger = logging.getLogger(name)
    logger.addHandler(DobermanLogger(db, name))
    logger.setLevel(logging.DEBUG)
    return logger

def make_hash(*args, hash_length=16):
    """
    Generates a hash from the provided arguments, returns
    a hex string
    :param *args: objects you want to be hashed. Will be converted to bytes
    :param hash_length: how long the returned hash should be. Default 16
    :returns: string
    """
    m = hashlib.sha256()
    map(lambda a: m.update(str(a).encode()), args)
    return m.hexdigest()[:hash_length]

def sensible_sig_figs(value, lowlim, upplim, defaultsigfigs=3):
    """
    Rounds a sensor measurement to a sensible number of significant figures.

    In general rounds to defaultsigfigs significant figures.
    If the lowlim and upplim are rather close, have at least
    one more than the number of decimal places to distinguish
    them. For example: with limits 1.023 and 1.044, sensor
    measurements have three decimal places.
    """
    mindps = 1 - floor(log10(upplim - lowlim))
    minsfs = floor(log10(value)) + 1 + mindps
    sfs = max(minsfs, defaultsigfigs)
    return f'{value:.{sfs}g}'


class SortedBuffer(object):
    """
    A custom semi-fixed-width buffer that keeps itself sorted
    """
    def __init__(self, length=None):
        self._buf = []
        self.length = length

    def __len__(self):
        return len(self._buf)

    def add(self, obj):
        """
        Adds a new object to the queue, time-sorted
        """
        LARGE_NUMBER = 1e12  # you shouldn't get timestamps larger than this
        if len(self._buf) == 0:
            self._buf.append(obj)
        elif len(self._buf) == 1:
            if self._buf[0]['time'] >= obj['time']:
                self._buf.insert(0, obj)
            else:
                self._buf.append(obj)
        else:
            idx = len(self._buf)//2
            for i in itertools.count(2):
                lesser = self._buf[idx-1]['time'] if idx > 0 else -1
                greater = self._buf[idx]['time'] if idx < len(self._buf) else LARGE_NUMBER
                if lesser <= obj['time'] <= greater:
                    self._buf.insert(idx, obj)
                    break
                elif obj['time'] > greater:
                    idx += max(1, len(self._buf)>>i)
                elif obj['time'] < lesser:
                    idx -= max(1, len(self._buf)>>i)
        if self.length is not None and len(self._buf) > self.length:
            self._buf = self._buf[-self.length:]
        return

    def pop_front(self):
        if len(self._buf) > 0:
            return self._buf.pop(0)
        raise ValueError('Buffer empty')

    def get_front(self):
        if len(self._buf) > 0:
            # copy
            return dict(self._buf[0].items())
        raise ValueError('Buffer empty')

    def __getitem__(self, index):
        return self._buf[index]

    def set_length(self, length):
        self.length = length

    def clear(self):
        self._buf = []

    def __iter__(self):
        return self._buf.__iter__()

