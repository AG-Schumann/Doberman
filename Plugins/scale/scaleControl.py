#! /usr/bin/env python3.3

import scaleMaster

class scaleControl(object):
    """
    Connection function between scaleMaster and slowControl
    Can not run on its own, use python scaleMaster.py -otps as a stand alone program instead
    """
    def __init__(self, opts):
        logger = opts.logger
        self.scale_master = scaleMaster.scaleMaster(opts, logger)

    def scalecontrol(self):
        self.scale_master.scalemaster()

    def __exit__(self):
        self.scale_master.__exit__()
