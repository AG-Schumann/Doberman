import Doberman
import threading
from functools import partial
import time

__all__ = 'Monitor'.split()


class Monitor(object):
    """
    A base monitor class
    """
    def __init__(self, db=None, _name=None, kafka_producer=None, loglevel='INFO'):
        """
        """
        if isinstance(self, Doberman.HostMonitor):
            self.name = db.hostname
        #elif isinstance(self, Doberman.AlarmMonitor):
        #    self.name='AlarmMonitor'
        elif isinstance(self, Doberman.SensorMonitor):
            self.name = _name
        self.db = db
        self.logger = Doberman.utils.Logger(name=self.name, db=self.db, loglevel=loglevel)
        self.sh = Doberman.utils.SignalHandler(self.logger)
        self.funcs = {}
        self.threads = {}
        self.events = {}
        self.Setup()
        self.RegisterFunction(func=self.HandleCommands, period=1, name='handlecommands')
        self.RegisterFunction(func=self.CheckThreads, period=30, name='checkthreads')

    def Close(self):
        """
        Joins all running threads
        """
        self.sh.run = False
        self.Shutdown()
        for k,(t, _)  in self.threads.items():
            try:
                self.should_run[k] = False
                t.join()
            except:
                pass
        for k,(t,_) in self.funcs.item():
            try:
                self.should_run[k] = False
                t.join()
            except:
                pass
        return

    def RegisterFunction(self, func, period, name, **kwargs):
        """
        Registers a function for the handler to call periodically and starts it

        :param func: the function to call. If it requires args, they should be kwargs.
                    Should return None (constant period) or a float (variable period)
        :param period: how many seconds between calls (initially, can be None if the
                    function returns floats).
        :param name: something unique to refer to a thread by
        :param kwargs: any keyword arguments required for func
        """
        self.logger.debug('Registering ' + name)
        func = partial(self.LoopHandler,
                        func=func if not kwargs else partial(func, **kwargs),
                        period=period,
                        name=name)
        self.StartFunction(name, func)
        return

    def RegisterThread(self, thread, target, name):
        """
        Registers a prepared (but not started) thread
        """
        self.logger.debug('Registering ' + name)
        thread.start()
        self.threads[name] = (thread, target)
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

    def StartFunction(self, name, func):
        """
        Starts a thread to handle a registered function
        """
        self.should_run[name] = threading.Event()
        t = threading.Thread(target=func)
        t.start()
        self.threads[name] = (t, func)

    def StopThread(self, name):
        """
        Stops a specific thread. Thread is not removed from thread dictionary
        """
        self.events[name].set()
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
        self.logger.debug('%s starting' % name)
        while self.sh.run and self.should_run[name]:
            loop_top = time.time()
            ret = func()
            if isinstance(ret, (int, float)) and 0. < ret:
                period = ret
            now = time.time()
            while (now - loop_top) < period and self.sh.run and self.should_run[name]:
                time_left = loop_top + period - now
                time.sleep(min(1, time_left))
                now = time.time()
        self.logger.debug('%s returning' % name)
        return


class FunctionHandler(threading.Thread):
    def __init__(self):
        threading.Thread.__init__()
        self.event = event
