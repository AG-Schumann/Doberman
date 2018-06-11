import os
import time
import datetime
import logging
import sys
from ReadoutThread import ReadoutThread


class Plugin(object):
    """
    Base plugin class. If you're seeing this then someone forgot to write a docstring for their own plugin
    """
    def __init__(self, opts):

        self.logger = logging.getLogger(__name__)
        self.opts = opts
        self.controller = None
        self.writer = None

        if not hasattr(self.opts, 'queue'):
            self.opts.queue = None

        self.writeThread = ReadoutThread(self.opts, self.writer, self.controller)

    def master(self):
        try:
            self.writeThread.start()
            runner = 0
            while runner < self._lives:
                runner += 1
                self.logger.info("Main program still alive...")
                if runner%2 == 0:
                    if self.writeThread.stopped or not self.writeThread.isAlive():
                        self.logger.fatal("Logging thread died! Reviving...")
                        self.writeThread.start()
                time.sleep(30)
            self.close()
        except KeyboardInterrupt:
            self.logger.fatal("Program killed by ctrl-c")
            self.close()

    def logHead(self):
        pass

    def close(self):
        self.logger.info("Closing the logger")
        self.writeThread.stopped = True
        self.writeThread.Tevent.set()
        self.writer.close()
        self.controller.close()
        return

    def __del__(self):
        self.close()
        return

    def __exit__(self):
        self.close()

