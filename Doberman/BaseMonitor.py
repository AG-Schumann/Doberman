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
        self.sh = Doberman.utils.SignalHandler(self.logger, self.event)
        self.setup()
        self.register(obj=self.check_threads, period=30, name='checkthreads')
        hn, port = self.db.get_listener_address(self.name)
        self.listener = Listener(hn, port, logger, self.event, self.process_command)
        self.listener.start()

    def __del__(self):
        pass

    def close(self):
        """
        Joins all running threads
        """
        self.event.set()
        self.shutdown()
        self.listener.join()
        pop = []
        thread_numbers = self.threads.keys()
        for thread_number in thread_numbers:
            try:
                self.threads[thread_number].event.set()
                self.threads[thread_number].join()
            except Exception as e:
                self.logger.debug(f'Can\'t close {thread_number}-thread. {e}')
            else:
                pop += [thread_number]
        map(self.threads.pop, pop)

    def register(self, name, obj, period=None, **kwargs):
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
            t = FunctionHandler(func=func, logger=self.logger, period=period, name=name)
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
        for n, t in list(self.threads.items()):
            if not t.is_alive():
                try:
                    self.logger.info(f'{n}-thread died')
                    self.stop_thread(n)
                except Exception as e:
                    self.logger.error(f'{n}-thread won\'t quit: {e}')

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
        self.period = period
        self.name = name

    def run(self):
        """
        Spawns a thread to do a function
        """
        self.logger.debug(f'Starting {self.name}')
        while not self.event.is_set():
            loop_top = time.time()
            self.logger.debug(f'Running {self.name}')
            ret = self.func()
            if isinstance(ret, (int, float)) and 0. < ret:
                self.period = ret
            self.event.wait(loop_top + self.period - time.time())
        self.logger.debug(f'Returning {self.name}')

class Listener(threading.Thread):
    """
    This class listens for incoming commands and handles them
    """
    def __init__(self, hostname, port, logger, event, process_command):
        threading.Thread.__init__(self)
        self.hostname = hostname
        self.port = port
        self.logger = logger
        self.event = event
        self.process_command = process_command
        self.packet_size = 2048

    def run(self):
        self.logger.debug('Listener starting up')
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            sock.bind((self.hostname, self.port))
            sock.listen()
            while not self.event.is_set():
                try:
                    conn, addr = sock.accept()
                    with conn:
                        data = conn.recv(self.packet_size).strip().decode()
                        self.process_command(data)
                except socket.timeout:
                    pass
                except Exception as e:
                    self.logger.info(f'Listener caught a {type(e)}: {e}')
        self.logger.debug('Listener shutting down')

