import Doberman
import threading
from functools import partial
import time
import zmq

__all__ = 'Monitor'.split()


class Monitor(object):
    """
    A base monitor class
    """

    def __init__(self, db=None, name=None, logger=None, debug=False):
        """
        """
        self.db = db
        self.logger = logger
        self.name = name
        self.debug = debug
        self.logger.info(f'Monitor "{name}" constructing')
        self.event = threading.Event()
        # we use a lock to synchronize access to the thread dictionary
        # we use an RLock because the thread that checks threads sometimes
        # also restarts threads, and starting threads requires locking the dictionary
        self.lock = threading.RLock()
        self.threads = {}
        self.restart_info = {}
        self.no_stop_threads = set()
        self.sh = Doberman.utils.SignalHandler(self.logger, self.event)
        self.db.notify_hypervisor(active=self.name)
        self.logger.info('Child setup starting')
        self.setup()
        self.logger.info('Child setup completed')
        time.sleep(1)
        self.register(obj=self.check_threads, period=30, name='check_threads', _no_stop=True)
        self.register(obj=self.listen, name='listen', _no_stop=True)


    def __del__(self):
        pass

    def close(self):
        """
        Joins all running threads
        """
        self.event.set()
        self.shutdown()
        pop = []
        with self.lock:
            for t in self.threads.values():
                # set the events all here because join() blocks
                t.event.set()
            for n, t in self.threads.items():
                try:
                    t.event.set()
                    t.join()
                except Exception as e:
                    self.logger.error(f'Can\'t close {n}-thread. {e}')
                else:
                    pop.append(n)
        map(self.threads.pop, pop)
        self.db.notify_hypervisor(inactive=self.name)

    def register(self, name, obj, period=None, _no_stop=False, **kwargs):
        """
        Register a new function/thing to be called regularly.

        :param name: the name of the thing
        :param obj: either a function or a threading.Thread
        :param period: how often (in seconds) you want this thing done. If obj is a
            function and returns a number, this will be used as the period. Default None
        :param _no_stop: bool, should this thread be allowed to stop? Default false
        :key **kwargs: any kwargs that obj needs to be called
        :returns: None
        """
        self.logger.info('Registering ' + name)
        if isinstance(obj, threading.Thread):
            # obj is a thread
            t = obj
            if not hasattr(t, 'event'):
                raise ValueError('Register received malformed object')
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
        with self.lock:
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
            self.logger.warning(f'Asked to stop thread {name}, but not permitted')
            return
        with self.lock:
            if name in self.threads:
                self.threads[name].event.set()
                self.threads[name].join()
                del self.threads[name]
            else:
                self.logger.warning(f'Asked to stop thread {name}, but it isn\'t in the dict')

    def check_threads(self):
        """
        Checks to make sure all threads are running. Attempts to restart any
        that aren't
        """
        with self.lock:
            for n, t in self.threads.items():
                if not t.is_alive():
                    self.logger.critical(f'{n}-thread died')
                    if n in self.restart_info:
                        try:
                            func, period = self.restart_info[n]
                            self.register(name=n, obj=func, period=period)
                        except Exception as e:
                            self.logger.error(f'{n}-thread won\'t restart: {e}')

    def listen(self):
        """
        Listens for incoming commands
        """
        host, ports = self.db.get_comms_info('command')
        ctx = zmq.Context.instance()
        incoming = ctx.socket(zmq.SUB)
        outgoing = ctx.socket(zmq.REQ)

        incoming.setsockopt_string(zmq.SUBSCRIBE, 'ping')
        incoming.setsockopt_string(zmq.SUBSCRIBE, self.name)

        incoming.connect(f'tcp://{host}:{ports["recv"]}')
        outgoing.connect(f'tcp://{host}:{ports["send"]}')

        poller = zmq.Poller()
        poller.register(incoming, zmq.POLLIN)

        while not self.event.is_set():
            socks = dict(poller.poll(timeout=1000))

            if socks.get(incoming) == zmq.POLLIN:
                msg = incoming.recv_string()
                if msg.startswith('ping'):
                    outgoing.send_string(f'pong {self.name}')
                    _ = outgoing.recv_string()
                else:
                    try:
                        # name, hash, command
                        _, cmd_hash, command = msg.split(' ', maxsplit=2)
                        if command == 'stop':
                            # We have to ack this before stopping
                            outgoing.send_string(f'ack {self.name} {cmd_hash}')
                        self.process_command(command)
                        outgoing.send_string(f'ack {self.name} {cmd_hash}')
                        _ = outgoing.recv_string()
                    except Exception as e:
                        self.logger.error(f'Caught a {type(e)} while processing command {command}: {e}')
                        self.logger.info(msg)

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
        self.logger.info(f'Starting {self.name}')
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
        self.logger.info(f'Returning {self.name}')
