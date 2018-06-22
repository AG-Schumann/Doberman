import time
import logging
from ReadoutThread import ReadoutThread
import Controller
import importlib
import importlib.machinery
from importlib.machinery import PathFinder

class Plugin(object):
    """
    Base plugin class. Attempts to find a controller with the specified name in the specified directory
    """
    def __init__(self, opts):

        self.logger = logging.getLogger(__name__)
        self.logger.debug('Starting...')
        self.name = opts.name
        
        spec = PathFiner.find_spec(name, opts.plugin_paths)
        if spec is None:
            raise FileNotFoundError('Could not find a controller named %s' % self.name)
        
        try:
            self.controller = getattr(spec.loader.load_module(), name)(opts)
        except Exception as e:
            raise FileNotFoundError('Could not load controller %s: %s' % (name, e))

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
            self.logger.fatal("Program killed by ctrl-c")
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

