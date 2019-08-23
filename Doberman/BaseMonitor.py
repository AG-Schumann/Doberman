import Doberman
import threading

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
        :param period: how many seconds between calls.
        :param kwargs: any keyword arguments required for func
        """
        self.funcs.append((func, period, **kwargs))

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
        for func, period, kwargs in self.funcs:
            t = threading.Thread(target=self.LoopHandler,
                    func=partial(func, **kwargs), period=period)
            t.start()
            self.threads.append((t, func, period, kwargs))

    def CheckThreads(self):
        """
        Checks to make sure all threads are running. Attempts to restart any
        that aren't
        """
        for i in range(len(self.threads)):
            t, f, p, kw = self.threads[i]
            if not t.is_alive():
                try:
                    self.info('%s-thread died, let\'s try restarting it' % str(f).split(' ')[1])
                    t.join()
                    t = threading.Thread(target=self.LoopHandler,
                            func=partial(f, **kw), period=p)
                    t.start()
                    self.threads[i] = (t, f, p, kw)
                except Exception as e:
                    self.logger.error('%s-thread died and won\'t restart' % str(f).split(' ')[1])
                    self.db.LogAlarm()  # TODO finish
                    _ = self.threads.pop(i)

    def HandleCommands(self):
        """
        A function for base classes to implement to handle any commands
        this instance should address
        """
        pass

    def LoopHandler(self, func, period):
        """
        Spawns a thread to do a function
        """
        while self.sh.run:
            loop_top = time.time()
            ret = func()
            if isinstance(ret, (int, float)) and 0. < ret:
                period = ret
            now = time.time()
            while (now - loop_top) < period and self.sh.run:
                time.sleep(max(1, now - loop_top))
                now = time.time()
