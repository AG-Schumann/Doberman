#! /usr/bin/env python3.3

import iseries1Master

class iseries1Control(object):
    """
    Connection function between iseries1Master and slowControl
    Can not run on its own, use python iseries1Master.py -otps as a stand alone program instead
    """
    def __init__(self, opts):
        logger = opts.logger
        self.iseries1_master = iseries1Master.iseries1Master(opts, logger)

    def iseries1control(self):
        self.iseries1_master.iseries1master()

    def __exit__(self):
        self.iseries1_master.__exit__()
