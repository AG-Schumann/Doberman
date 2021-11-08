import Doberman
import threading
from functools import partial
import time

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
        if threading.current_thread() is threading.main_thread():
            self.sh = Doberman.utils.SignalHandler(self.logger, self.event)
        self.setup()
        self.register(obj=self.handle_commands, period=1, name='handlecommands')
        self.register(obj=self.check_threads, period=30, name='checkthreads')

    def __del__(self):
        self.close()

    def __exit__(self):
        self.close()

    def close(self):
        """
        Joins all running threads
        """
        self.event.set()
        self.shutdown()
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
        for p in pop:
            self.threads.pop(p)

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
            t = FunctionHandler(func=func, logger=self.logger, period=period, event=self.event, name=name)
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

    def handle_commands(self):
        """
        A function for base classes to implement to handle any commands
        this instance should address
        """


class FunctionHandler(threading.Thread):
    def __init__(self, func=None, logger=None, period=None, event=None, name=None):
        threading.Thread.__init__(self)
        self.event = event
        self.func = func
        self.logger = logger
        self.period = period
        self.name = name
        if threading.current_thread() is threading.main_thread():
            self.sh = Doberman.utils.SignalHandler(logger, self.event)

    def run(self):
        """
        Spawns a thread to do a function
        """
        self.logger.debug('Starting')
        while not self.event.is_set():
            loop_top = time.time()
            self.logger.debug(f'Running {self.name}')
            ret = self.func()
            if isinstance(ret, (int, float)) and 0. < ret:
                self.period = ret
            self.event.wait(loop_top + self.period - time.time())
        self.logger.debug('Returning')
