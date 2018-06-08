#! /usr/bin/env python3.3

import iseries4Master

class iseries4Control(object):
    """
    Connection function between iseries4Master and slowControl
    Can not run on its own, use python iseries4Master.py -otps as a stand alone program instead
    """
    def __init__(self, opts):
        logger = opts.logger
        self.iseries4_master = iseries4Master.iseries4Master(opts, logger)

    def iseries4control(self):
        self.iseries4_master.iseries4master()

    def __exit__(self):
        self.iseries4_master.__exit__()
