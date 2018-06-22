import time
import logging
from ReadoutThread import ReadoutThread
import Controller

class Plugin(object):
    """
    Base plugin class. If you're seeing this then someone forgot to write a docstring for their own plugin.
    Your c'tor must create its self.controller before calling __init__
    on its parent
    """
    def __init__(self, opts):

        self.logger = logging.getLogger(__name__)
        self.logger.debug('Starting...')
        self.controller = None

        self.writeThread = ReadoutThread(opts, self.logger, self.controller)

    def Run(self):
        """This function starts the readout process from the controller.
        It spawns a new thread and checks periodically if it's still running.
        If it isn't it tries to restart it
        """
        yesno = False
        try:
            self.writeThread.start()
            self.writeThread.running = True
            while True:
                self.logger.debug("Main program still alive...")
                if yesno:
                    if not self.writeThread.running or not self.writeThread.isAlive():
                        self.logger.fatal("Readout thread died! Reviving...")
                        self.writeThread.start()
                time.sleep(30)
                yesno = not yesno
            self.close()
        except KeyboardInterrupt:
            self.logger.fatal("\n\nProgram killed by ctrl-c\n\n")
            self.close()

    def close(self):
        self.logger.debug("Closing...")
        self.writeThread.running = False
        self.writeThread.Tevent.set()
        self.controller.close()
        return

    def __del__(self):
        self.close()
        return

    def __exit__(self):
        self.close()

