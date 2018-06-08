#! /usr/bin/env python3.3

import iseries2Master

class iseries2Control(object):
    """
    Connection function between iseries2Master and slowControl
    Can not run on its own, use python iseries2Master.py -otps as a stand alone program instead
    """
    def __init__(self, opts):
        logger = opts.logger
        self.iseries2_master = iseries2Master.iseries2Master(opts, logger)

    def iseries2control(self):
        self.iseries2_master.iseries2master()

    def __exit__(self):
        self.iseries2_master.__exit__()
