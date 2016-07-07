#! /usr/bin/env python3.3

import caen_n1470Master

class caen_n1470Control(object):
    """
    Connection function between caen_n1470Master and slowControl
    Can not run on its own, use python caen_n1470Master.py -otps as a stand alone program instead
    """
    def __init__(self, opts):
        logger = opts.logger
        if len(opts.additional_parameters) == 3:
            if not opts.additional_parameters[2] == '':
                opts.BDname = opts.additional_parameters[2]
            if not opts.additional_parameters[1] == '':
	            opts.SN = opts.additional_parameters[1]
            if not opts.additional_parameters[0] == '':
	            opts.moduleadr = opts.additional_parameters[0]
        elif len(opts.additional_parameters) == 2:
            if not opts.additional_parameters[1] == '':
	            opts.SN = opts.additional_parameters[1]
            if not opts.additional_parameters[0] == '':
	            opts.moduleadr = opts.additional_parameters[0]
        elif len(opts.additional_parameters) == 1:
            if not opts.additional_parameters[0] == '':
	            opts.moduleadr = opts.additional_parameters[0]
        self.caen_n1470_master = caen_n1470Master.caen_n1470Master(opts, logger)

    def caen_n1470control(self):
        self.caen_n1470_master.caen_n1470master()

    def __exit__(self):
        self.caen_n1470_master.__exit__()
