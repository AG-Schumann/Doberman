import Doberman
import threading
from functools import partial
import time
import socket

__all__ = 'Monitor'.split()


class Monitor(object):
    """
    A base monitor class
    """

    def __init__(self, db=None, name=None, logger=None):
        """
        """
        self.db = db
        self.logger = logger
        self.name = name
        self.logger.debug('Monitor constructing')
        self.event = threading.Event()
        self.threads = {}
        self.restart_info = {}
        self.no_stop_threads = set()
        self.sh = Doberman.utils.SignalHandler(self.logger, self.event)
        self.register(obj=self.check_threads, period=30, name='checkthreads', _no_stop=True)
        _, port = self.db.assign_listener_address(self.name)
        l = Listener(port, logger, self.event, lambda cmd: self.process_command(cmd))
        self.register(name='listener', obj=l, _no_stop=True)
        self.setup()

    def __del__(self):
        pass

    def close(self):
        """
        Joins all running threads
        """
        self.event.set()
        self.shutdown()
        self.db.release_listener_port(self.name)
        pop = []
        for n, t in self.threads.items():
            try:
                t.event.set()
                t.join()
            except Exception as e:
                self.logger.debug(f'Can\'t close {n}-thread. {e}')
            else:
                pop.append(n)
        map(self.threads.pop, pop)

    def register(self, name, obj, period=None, _no_stop=False, **kwargs):
        """
        Register a new function/thing to be called regularly.

        :param name: the name of the thing
        :param obj: either a function or a threading.Thread
        :param period: how often (in seconds) you want this thing done. If obj is a
            function and returns a number, this will be used as the period. Default None
        :param _no_stop: bool, should this thread be allowed to stop? Default false
        :param **kwargs: any kwargs that obj needs to be called
        :returns: None
        """
        self.logger.debug('Registering ' + name)
        if isinstance(obj, threading.Thread):
            # obj is a thread
            t = obj
            if not hasattr(t, 'event'):
                raise ValueError('Register received misformed object')
        else:
            # obj is a function, must wrap with FunctionHandler
            if kwargs:
                func = partial(obj, **kwargs)
            else:
                func = obj
            self.restart_info[name] = (func, period)  # store for restarting later if necessary
            t = FunctionHandler(func=func, logger=self.logger, period=period, name=name)
        if _no_stop:
            self.no_stop_threads.add(name)
        t.start()
        self.threads[name] = t

    def setup(self, *args, **kwargs):
        """
        Called by the constructor. Allows subclasses to initialize stuff (most
        notably calls to Register)
        """

    def shutdown(self):
        """
        Called when the monitor begins its shutdown sequence. sh.run will have been
        set to False before this is called, and all threads will be joined once
        this function returns
        """

    def stop_thread(self, name):
        """
        Stops a specific thread. Thread is removed from thread dictionary
        """
        if name in self.no_stop_threads:
            self.logger.error(f'Asked to stop thread {name}, but not permitted')
            return
        if name in self.threads:
            self.threads[name].event.set()
            self.threads[name].join()
            del self.threads[name]
        else:
            self.logger.info(f'Asked to stop thread {name}, but it isn\'t in the dict')

    def check_threads(self):
        """
        Checks to make sure all threads are running. Attempts to restart any
        that aren't
        """
        for n, t in self.threads.items():
            if not t.is_alive():
                self.logger.critical(f'{n}-thread died')
                if n in self.restart_info:
                    try:
                        func, period = self.restart_info[n]
                        self.register(name=n, obj=func, period=period)
                    except Exception as e:
                        self.logger.error(f'{n}-thread won\'t restart: {e}')

    def process_command(self, command):
        """
        A function for base classes to implement to handle any commands
        this instance should address.

        :param command: string, something to handle
        """
        pass


class FunctionHandler(threading.Thread):
    def __init__(self, func=None, logger=None, period=None, event=None, name=None):
        threading.Thread.__init__(self)
        self.event = event or threading.Event()
        self.func = func
        self.logger = logger
        self.period = period or 10
        self.name = name

    def run(self):
        """
        Spawns a thread to do a function
        """
        self.logger.debug(f'Starting {self.name}')
        while not self.event.is_set():
            loop_top = time.time()
            try:
                self.logger.debug(f'Running {self.name}')
                ret = self.func()
                if isinstance(ret, (int, float)) and 0. < ret:
                    self.period = ret
            except Exception as e:
                self.logger.error(f'{self.name} caught a {type(e)}: {e}')
            self.event.wait(loop_top + self.period - time.time())
        self.logger.debug(f'Returning {self.name}')


class Listener(threading.Thread):
    """
    This class listens for incoming commands and handles them
    """

    def __init__(self, port, logger, event, process_command):
        threading.Thread.__init__(self)
        self.port = port
        self.logger = logger
        self.event = event
        self.process_command = process_command
        self.packet_size = 2048

    def run(self):
        self.logger.debug('Listener starting up')
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            sock.bind(('', self.port))
            sock.listen()
            while not self.event.is_set():
                data = None
                addr = None
                try:
                    conn, addr = sock.accept()
                    with conn:
                        data = conn.recv(self.packet_size).strip().decode()
                        self.process_command(data)
                except socket.timeout:
                    pass
                except Exception as e:
                    self.logger.info(f'Listener caught a {type(e)} while handling {data} from {addr}: {e}')
        self.logger.debug('Listener shutting down')
