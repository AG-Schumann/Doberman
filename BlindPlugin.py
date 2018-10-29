from Plugin import Plugin
import logging


class BlindPlugin(Plugin):
    """
    Special class to handle output-only controllers that might be
    used with feedback controllers. Basically doesn't do anything
    other than handle commands.
    """

    def Readout(self, rundoc):
        return

    def ProcessData(self, data, configdoc):
        return
