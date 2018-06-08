#! /usr/bin/env python3.3

import iseries3Master

class iseries3Control(object):
    """
    Connection function between iseries3Master and slowControl
    Can not run on its own, use python iseries3Master.py -otps as a stand alone program instead
    """
    def __init__(self, opts):
        logger = opts.logger
        self.iseries3_master = iseries3Master.iseries3Master(opts, logger)

    def iseries3control(self):
        self.iseries3_master.iseries3master()

    def __exit__(self):
        self.iseries3_master.__exit__()
