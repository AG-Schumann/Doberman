from BasePlugin import Plugin


class BlindPlugin(Plugin):
    """
    Special class to handle output-only sensors that might be
    used with feedback controllers. Basically doesn't do anything
    other than handle commands.
    """

    def ReadoutLoop(self, i):
        return

    def ProcessReading(self, index, timestamp, value, retcode):
        return
