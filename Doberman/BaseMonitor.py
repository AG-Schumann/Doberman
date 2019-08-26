import Doberman
import threading
from functools import partial
import time

__all__ = 'Monitor'.split()


class Monitor(object):
    """
    A base monitor class
    """
    def __init__(self, _name, db, autostart=False):
        """
        """
        self.name = _name
        self.db = db
        self.logger = Doberman.utils.Logger(name=self.name, db=self.db)
        self.sh = Doberman.utils.SignalHandler(self.logger)
        self.threads = []
        self.funcs = []
        self.Setup()
        if autostart:
            self.StartThreads()

    def Close(self):
        """
        Joins all running threads
        """
        self.sh.run = False
        self.Shutdown()
        for t, _, _, _ in self.threads:
            try:
                t.join()
            except:
                pass

    def Register(self, func, period, **kwargs):
        """
        Register a function for the handler to call periodically.

        :param func: the function to call. If it requires args, they should be kwargs.
                    Should return None (constant period) or a float (variable period)
        :param period: how many seconds between calls (initially, can be None if the
                    function returns floats).
        :param kwargs: any keyword arguments required for func
        """
        self.funcs.append((func, period, kwargs))

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

    def StartThreads(self):
        """
        Starts all registered functions
        """
        self.Register(func=self.HandleCommands, period=1)
        self.Register(func=self.CheckThreads, period=30)
        for fcn, period, kwargs in self.funcs:
            part = partial(self.LoopHandler, func=partial(fcn, **kwargs), period=period)
            t = threading.Thread(target=part)
            t.start()
            self.threads.append((t, part))

    def CheckThreads(self):
        """
        Checks to make sure all threads are running. Attempts to restart any
        that aren't
        """
        for i, (t,f) in enumerate(self.threads):
            if not t.is_alive():
                try:
                    self.logger.info('%s-thread died, let\'s try restarting it' % f.split(' ')[2])
                    t.join()
                    t = threading.Thread(target=f)
                    t.start()
                    self.threads[i] = (t, f)
                except Exception as e:
                    self.logger.error('%s-thread died and won\'t restart' % f.split(' ')[2])
                    self.db.LogAlarm()  # TODO finish
                    _ = self.threads.pop(i)

    def HandleCommands(self):
        """
        A function for base classes to implement to handle any commands
        this instance should address
        """
        pass

    def LoopHandler(self, func=None, period=None):
        """
        Spawns a thread to do a function
        """
        self.logger.debug('%s starting' % str(func).split(' ')[2])
        while self.sh.run:
            loop_top = time.time()
            ret = func()
            if isinstance(ret, (int, float)) and 0. < ret:
                period = ret
            now = time.time()
            while (now - loop_top) < period and self.sh.run:
                time.sleep(min(1, now - loop_top))
                now = time.time()
        self.logger.debug('%s returning' % str(func).split(' ')[2])
