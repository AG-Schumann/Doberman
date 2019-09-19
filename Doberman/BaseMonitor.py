import Doberman
import threading
from functools import partial
import time

__all__ = 'Monitor'.split()


class Monitor(object):
    """
    A base monitor class
    """
    def __init__(self, db=None, _name=None, loglevel='INFO'):
        """
        """
        if isinstance(self, Doberman.HostMonitor):
            self.name = db.hostname
        #elif isinstance(self, Doberman.AlarmMonitor):
        #    self.name='AlarmMonitor'
        elif isinstance(self, Doberman.SensorMonitor):
            self.name = _name
        self.db = db
        self.logger = Doberman.utils.Logger(name=self.name, db=db, loglevel=loglevel)
        self.sh = Doberman.utils.SignalHandler(self.logger)
        self.threads = {}
        self.Setup()
        self.Register(obj=self.HandleCommands, period=1, name='handlecommands')
        self.Register(obj=self.CheckThreads, period=30, name='checkthreads')
        self.loglevel = loglevel

    def __del__(self):
        self.Close()
        return

    def __exit__(self):
        self.Close()
        return

    def Close(self):
        """
        Joins all running threads
        """
        self.sh.run = False
        self.Shutdown()
        for n,t in self.threads.items():
            try:
                t.event.set()
                t.join()
            except:
                pass
        return

    def Register(self, name, obj, period=None, **kwargs):
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
            t = FunctionHandler(func=func, logger=self.logger, period=period)
        t.start()
        self.threads[name] = t
        return

    def Setup(self, *args, **kwargs):
        """
        Called by the constructor. Allows subclasses to initialize stuff (most
        notably calls to Register)
        """
        pass

    def Shutdown(self):
        """
        Called when the monitor begins its shutdown sequence. sh.run will have been
        set to False before this is called, and all threads will be joined once
        this function returns
        """
        pass

    def StopThread(self, name):
        """
        Stops a specific thread. Thread is removed from thread dictionary
        """
        self.threads[name].event.set()
        self.threads[name].join()
        del self.threads[name]
        return

    def CheckThreads(self):
        """
        Checks to make sure all threads are running. Attempts to restart any
        that aren't
        """
        for n, t in list(self.threads.items()):
            if not t.is_alive():
                try:
                    self.logger.info('%s-thread died' % n)
                    self.StopThread(n)
                except Exception as e:
                    self.logger.error('%s-thread won\'t quit' % n)
        return

    def HandleCommands(self):
        """
        A function for base classes to implement to handle any commands
        this instance should address
        """
        pass

class FunctionHandler(threading.Thread):
    def __init__(self, func=None, logger=None, period=None):
        threading.Thread.__init__()
        self.event = threading.Event()
        self.func = func
        self.logger = logger
        self.period = period
        self.sh = Doberman.utils.SignalHandler(logger, self.event)

    def run(self):
        """
        Spawns a thread to do a function
        """
        self.logger.debug('Starting')
        while not self.event.is_set():
            loop_top = time.time()
            ret = self.func()
            if isinstance(ret, (int, float)) and 0. < ret:
                self.period = ret
            self.event.wait(loop_top + self.period - time.time())
        self.logger.debug('Returning')
        return
