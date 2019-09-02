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
        elif isinstance(self, Doberman.AlarmMonitor):
            self.name='AlarmMonitor'
        elif isinstance(self, Doberman.SensorMonitor):
            self.name = _name
        self.db = db
        self.logger = Doberman.utils.Logger(name=self.name, db=self.db, loglevel=loglevel)
        self.sh = Doberman.utils.SignalHandler(self.logger)
        self.threads = {}
        self.should_run = {}
        self.Setup()
        self.Register(func=self.HandleCommands, period=1, name='handlecommands')
        self.Register(func=self.CheckThreads, period=30, name='checkthreads')

    def Close(self):
        """
        Joins all running threads
        """
        self.sh.run = False
        self.Shutdown()
        for t, _  in self.threads.items():
            try:
                t.join()
            except:
                pass

    def Register(self, func, period, name, **kwargs):
        """
        Registers a function for the handler to call periodically and starts it

        :param func: the function to call. If it requires args, they should be kwargs.
                    Should return None (constant period) or a float (variable period)
        :param period: how many seconds between calls (initially, can be None if the
                    function returns floats).
        :param name: something unique to refer to a thread by
        :param kwargs: any keyword arguments required for func
        """
        func = partial(self.LoopHandler,
                        func=(partial(func, **kwargs),
                            period=period,
                            name=name))))
        self.StartThread(name, func)

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

    def StartThread(self, name, func):
        """
        Starts a thread
        """
        self.should_run[name] = True
        t = threading.Thread(target=func)
        t.start()
        self.threads[name] = (t, func)

    def StopThread(self, name):
        """
        Stops a specific thread. Thread is not removed from thread dictionary
        """
        self.should_run[name] = False
        try:
            self.threads[name][0].join()
        except Exception as e:
            self.logger.error('Tried to stop %s-thread but failed!' % name)

    def CheckThreads(self):
        """
        Checks to make sure all threads are running. Attempts to restart any
        that aren't
        """
        to_remove = []
        for n, (t,f) in self.threads.items():
            if not t.is_alive():
                try:
                    self.logger.info('%s-thread died, let\'s try restarting it' % n)
                    self.StopThread(n)
                    self.StartThread(n,f)
                except Exception as e:
                    self.logger.error('%s-thread died and won\'t restart' % n)
                    self.db.LogAlarm()  # TODO finish
                    try:
                        self.StopThread(n)
                    except Exception as e:
                        pass
                    to_remove.append(n)
        for n in to_remove:
            # can't call this during the above loop
            del self.threads[n]

    def HandleCommands(self):
        """
        A function for base classes to implement to handle any commands
        this instance should address
        """
        pass

    def LoopHandler(self, func=None, period=None, name=None):
        """
        Spawns a thread to do a function
        """
        self.logger.debug('%s starting' % n)
        while self.sh.run and self.should_run[name]:
            loop_top = time.time()
            ret = func()
            if isinstance(ret, (int, float)) and 0. < ret:
                period = ret
            now = time.time()
            while (now - loop_top) < period and self.sh.run and self.should_run[name]:
                time.sleep(min(1, now - loop_top))
                now = time.time()
        self.logger.debug('%s returning' % n)
