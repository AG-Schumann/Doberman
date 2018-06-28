import threading
import datetime


class ReadoutThread(threading.Thread):
    """Class that controls starting, running, and stopping the readout thread
    """

    def __init__(self, opts, logger, controller):

        self.ReadoutInterval = 30
        self.logger = logger
        self.queue = opts.queue
        self.controller = controller

        if 5 <= opts.readout_interval and opts.readout_interval < 1000:
            self.ReadoutInterval = self.opts.readout_interval
            self.logger.info("Readout interval set to %i sec." % self.ReadoutInterval)
        else:
            self.logger.error("Invalid readout interval. Using default 30 sec.")

        self.running = False
        super().__init__()
        self.Tevent = threading.Event()

    def run(self):
        while self.running:
            self.Readout()
            self.Tevent.wait(self.ReadoutInterval)

    def Readout(self):
        """
        Actually interacts with the device. Pushes [name, time, data, status] upstream
        """
        vals = self.controller.Readout()
        if vals['data'] is not None and not isinstance(vals['data'], (list, tuple)):
            vals['data'] = [vals['data']]
        if not isinstance(vals['retcode'], (list, tuple)):
            vals['retcode'] = [vals['retcode']]
        upstream = [self.controller.name, datetime.datetime.now(),
                    vals['data'],vals['retcode']]
        self.queue.put(upstream)
        return
