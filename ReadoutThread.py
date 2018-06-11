import threading
import logging


class ReadoutThread(threading.Thread):
    """Class that controls starting, running, and stopping the readout thread
    """

    def __init__(self, opts, writer, controller):

        self.ReadoutInterval = 30
        self.logger = logging.getLogger(__name__)
        self.opts = opts
        self.writer = writer
        self.controller = controller

        if 5 <= self.opts.loginterval and self.opts.loginterval < 1000:
            self.ReadoutInterval = self.opts.loginterval
            self.logger.info("Readout interval set to %i sec." % self.ReadoutInterval)
        else:
            self.logger.error("Invalid readout interval. Using default 30 sec.")

        self.stopped = False
        thread.Thread.__init__(self)
        self.Tevent = threading.Event()

    def run(self):
        while not self.stopped:
            self.ReadoutT()
            self.Tevent.wait(self.ReadoutInterval)

    def ReadoutT(self):
        """
        Actually interacts with the device. Defines the readout format.
        """
        raise NotImplementedError
