import time
import logging
from ReadoutThread import ReadoutThread
import importlib
import importlib.machinery
from importlib.machinery import PathFinder
from DobermanDB import DobermanDB
import DobermanLogger
import argparse


class Plugin(object):
    """
    Base plugin class. Attempts to find a controller with the specified name in the specified directory
    """
    def __init__(self, opts):
        self.logger = logging.getLogger(opts.name)
        self.name = opts.name
        self.logger.debug('Starting %s...' % self.name)
        if self.name != 'RAD7':
            plugin_name = self.name.rstrip('0123456789')
        else:
            plugin_name = self.name

        spec = PathFinder.find_spec(plugin_name, opts.plugin_paths)
        if spec is None:
            raise FileNotFoundError('Could not find a controller named %s' % plugin_name)
        try:
            controller_ctor = getattr(spec.loader.load_module(), plugin_name)
        except Exception as e:
            raise FileNotFoundError('Could not load controller %s: %s' % (plugin_name, e))

        self.writeThread = ReadoutThread(opts, self.logger, controller_ctor)

    def Run(self):
        """This function starts the readout process from the controller.
        It spawns a new thread and checks periodically if it's still running.
        If it isn't it tries to restart it
        """
        yesno = False
        try:
            self.writeThread.running = True
            self.writeThread.start()
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
        self.logger.debug("Closing %s..." % self.name)
        self.writeThread.running = False
        self.writeThread.Tevent.set()
        self.controller.close()
        return

    def __del__(self):
        self.close()
        return

    def __exit__(self):
        self.close()
        return

def main():
    parser = argparse.ArgumentParser(description='Doberman standalone plugin')
    parser.add_argument('--name', type=str, dest='plugin_name',
                        help='Name of the controller', required=True)
    parser.add_argument('--config', type=str, dest='configuration',
                        help='Which configuration to run with', default='default')
    parser.add_argument('--log', type=int, choices=range(10,60,10), default=20,
                        help='Logging level')
    args = parser.parse_args()
    logging.getLogger()
    logger.addHandler(DobermanLogger.DobermanLogger())
    db = DobermanDB()

    return

if __name__ == '__main__':
    main()
