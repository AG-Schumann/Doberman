import time
import logging
import DobermanDB
import datetime
import utils
dtnow = datetime.datetime.now


class Monitor(object):
    """
    Generic class to handle system monitoring
    """
    def __init__(self, db):
        self.db = db

        self.Startup()

    def Startup(self):
        """
        A function for derived classes to implement for things they want
        done during plugin startup
        """
        pass

    def close(self):
        self.db = None
        return

    def __del__(self):
        self.close()
        return

    def __exit__(self):
        self.close()
        return

    def Overwatch(self):
        """
        A function for derived classes to implement for whatever actions
        they want called while the plug is active
        """
        pass

    def LoopFcn(self):
        self.sleep = False
        loop_timer = utils.heartbeat_timer
        self.logger.info('Beginning monitor loop')
        sh = utils.SignalHandler(self.logger)
        self.start_time = dtnow()
        try:
            while not sh.interrupted:
                loop_start_time = time.time()
                self.Heartbeat()
                if not self.sleep:
                    self.CheckCommands()
                    self.Overwatch()
                while (time.time() - loop_start_time) < loop_time and not sh.interrupted:
                    time.sleep(1)
                    self.CheckCommands()
        except Exception as e:
            self.logger.fatal('Monitor loop caught fatal %s exception: %s' % (type(e), str(e)))
        finally:
            self.close()
            return

    def Heartbeat(self):
        self.db.Heartbeat()
        live_hosts = self.db.GetLiveHosts()
        for host in live_hosts:
            if self.db.CheckHeartbeat(hostname=host) > 3*utils.heartbeat_timer:
                # host hasn't heartbeated recently
