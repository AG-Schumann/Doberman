#! /usr/bin/env python3.3

import TeledyneMaster

class TeledyneControl(object):
    """
    Connection function between TeledyneMaster and slowControl
    Can not run on its own, use python TeledyneMaster.py -otps as a stand alone program instead
    """
    def __init__(self, opts):
        logger = opts.logger
        self.Teledyne_master = TeledyneMaster.TeledyneMaster(opts, logger)

    def Teledynecontrol(self):
        self.Teledyne_master.Teledynemaster()

    def __exit__(self):
        self.Teledyne_master.__exit__()
