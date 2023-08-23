import importlib
import importlib.machinery
import datetime
import signal
import os.path
import os
import logging
import logging.handlers
from pytz import utc
import threading
import hashlib
from math import floor, log10
import itertools

number_regex = r'[\-+]?[0-9]+(?:\.[0-9]+)?(?:[eE][\-+]?[0-9]+)?'


def dtnow():
    return datetime.datetime.now(tz=utc)  # no timezone nonsense, now


def find_plugin(name, path):
    """
    Finds the device constructor with the specified name, in the specified paths.
    Will attempt to strip numbers off the end of the name if necessary (ex,
    'iseries1' -> iseries, 'caen_n1470' -> caen_n1470)

    :param name: the name of the device you want
    :param path: a list of paths in which to search for the file
    :returns constructor: the constructor of the requested device
    """
    if not isinstance(path, (list, tuple)):
        path = [path]
    plugin_name = name
    spec = importlib.machinery.PathFinder.find_spec(plugin_name, path)
    if spec is None:
        plugin_name = name.strip('0123456789')
        spec = importlib.machinery.PathFinder.find_spec(plugin_name, path)
    if spec is None:
        plugin_name = name.rsplit('_', 1)[0]
        spec = importlib.machinery.PathFinder.find_spec(plugin_name, path)
    if spec is None:
        raise FileNotFoundError(f'Could not find a device named {name} in {path}')
    try:
        device_ctor = getattr(spec.loader.load_module(), plugin_name)
    except AttributeError:
        raise AttributeError(f'Could not find constructor for {name}')
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
            self.logger.info(f'Received signal {args[0]}')
        self.signal_number = int(args[0])
        self.run = False
        if self.event is not None:
            self.event.set()


class DobermanLogger(logging.Handler):
    """
    A custom logging handler.
    """

    def __init__(self, db, name, output_handler):
        logging.Handler.__init__(self)
        self.db = db
        self.name = name
        self.collection_name = 'logs'
        self.oh = output_handler

    def emit(self, record):
        msg_datetime = datetime.datetime.fromtimestamp(record.created)
        msg_date = datetime.date(msg_datetime.year, msg_datetime.month, msg_datetime.day)
        m = self.format_message(msg_datetime, record.levelname, record.funcName, record.lineno, record.getMessage())
        self.oh.write(m, msg_date)
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


class OutputHandler(object):
    """
    We need a single object that owns the file we log to,
    so we can pass references to it to child loggers.
    I don't know how to do c++-style static class members,
    so this is how I solve this problem.
    Files go to /global/logs/<experiment>/YYYY/MM.DD, folders being created as necessary.
    """
    __slots__ = ('mutex', 'filename', 'experiment', 'f', 'today', 'flush_cycle', 'debug')

    def __init__(self, name, experiment, debug=False):
        self.mutex = threading.Lock()
        self.filename = f'{name}.log'
        self.experiment = experiment
        self.f = None
        self.flush_cycle = 0
        self.rotate()
        self.debug = debug

    def rotate(self):
        if self.f is not None:
            self.f.close()
        self.today = datetime.date.today()
        logdir = f'/global/logs/{self.experiment}/{self.today.year}/{self.today.month:02d}.{self.today.day:02d}'
        os.makedirs(logdir, exist_ok=True)
        full_path = os.path.join(logdir, self.filename)
        self.f = open(full_path, 'a')

    def write(self, message, date):
        with self.mutex:
            # we wrap anything hitting files or stdout with a mutex because logging happens from
            # multiple threads, and files aren't thread-safe
            if date != self.today:
                # it's a brand-new day, and the sun is high...
                self.rotate()
            if message[-1] == '\n':
                message = message[:-1]
            print(message)
            self.f.write(f'{message}\n')
            self.flush_cycle += 1
            if self.flush_cycle > 3:
                # if we don't regularly flush the buffers, messages will sit around in memory rather than actually
                # get pushed to disk, and we don't want this. If we do it too frequently it's slow
                self.f.flush()
                self.flush_cycle = 0

    def get_logdir(self, date):
        return f'/global/logs/{self.experiment}/{date.year}/{date.month:02d}.{date.day:02d}'


def get_logger(name, db, debug=False):
    oh = OutputHandler(name, db.experiment_name, debug)
    logger = logging.getLogger(name)
    logger.addHandler(DobermanLogger(db, name, oh))
    if debug:
        logger.setLevel(logging.DEBUG)
    return logger


def get_child_logger(name, db, main_logger):
    logger = logging.getLogger(name)
    if logger.hasHandlers():
        logger.handlers.clear()
    logger.addHandler(DobermanLogger(db, name, main_logger.handlers[0].oh))
    if main_logger.handlers[0].oh.debug:
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
            idx = len(self._buf) // 2
            for i in itertools.count(2):
                lesser = self._buf[idx - 1]['time'] if idx > 0 else -1
                greater = self._buf[idx]['time'] if idx < len(self._buf) else LARGE_NUMBER
                if lesser <= obj['time'] <= greater:
                    self._buf.insert(idx, obj)
                    break
                elif obj['time'] > greater:
                    idx += max(1, len(self._buf) >> i)
                elif obj['time'] < lesser:
                    idx -= max(1, len(self._buf) >> i)
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
