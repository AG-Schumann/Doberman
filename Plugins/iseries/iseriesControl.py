#! /usr/bin/env python3.3

import iseriesMaster

class iseriesControl(object):
    """
    Connection function between iseriesMaster and slowControl
    Can not run on its own, use python iseriesMaster.py -otps as a stand alone program instead
    """
    def __init__(self, opts):
        logger = opts.logger
        self.iseries_master = iseriesMaster.iseriesMaster(opts, logger)

    def iseriescontrol(self):
        self.iseries_master.iseriesmaster()

    def __exit__(self):
        self.iseries_master.__exit__()
