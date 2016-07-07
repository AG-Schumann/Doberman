import datetime
import os
import Queue
import logging
import DobermanDB


class DobermanCommunication(object):
    """
    Passes data to the Doberman slow control program over a queue.
    Tests the values first.
    Important: Pass the logger if you using any, otherways it can produce
       duplicated logging output.
    """

    def __init__(self, queue, name, logger=None):
        self.logger = logger
        self.queue = queue
        self.name = name

        if not self.logger:
            loglevel = 20
            logger = logging.getLogger()
            logger.setLevel(int(loglevel))
            chlog = logging.StreamHandler()
            chlog.setLevel(int(loglevel))
            formatter = logging.Formatter('%(levelname)s:%(process)d:%'
                                          '(module)s:%(funcName)s:%(lineno)d:%'
                                          '(message)s')
            chlog.setFormatter(formatter)
            logger.addHandler(chlog)
            logger.info("No logger given. Addeed default logger with "
                        "loglevel %s" % str(loglevel))
            self.logger = logger

    def pushToQueue(self, data, status=None, logtime=None):
        '''
        Writes the to the queue.
        Checks that the values have the right type first.
        Use the formats:
          data: [float],
          status: [int],
          logtime: datetime.datetme
        '''
        # Check time format
        if not logtime:
            logtime = datetime.datetime.now()
        elif type(logtime) != datetime.datetime:
            self.logger.warning("Logtime has wrong format. Replaced by "
                                "the current time (%s)" %
                                str(logtime.strftime('%Y-%m-%d | %H:%M:%S')))
            logtime = datetime.datetime.now()
        # Check data format
        if type(data) != list:
            if type(data) == tuple:
                data = list(data)
            else:
                data = [data]
        for ii, item in enumerate(data):
            if not isinstance(item, float):
                try:
                    data[ii] = float(item)
                except Exception as e:
                    self.logger.warning("Data (%s) can not be saved as float. "
                                        "Error: %s" % (str(data), e))
                    return -1
        # Check status format
        if not status:
            status = [-2] * len(data)
        elif not isinstance(status, list):
            if isinstance(status, tuple):
                status = list(status)
            else:
                status = [status]
        for ii, item in enumerate(status):
            if not isinstance(item, int):
                try:
                    status[ii] = [int(item)]
                except Exception as e:
                    self.logger.warning("Status[%d] (%s) can not be saved "
                                        "as int. Replaced status by [-2]. "
                                        "Error: %s" % (ii, str(status[ii]), e))
                    status[ii] = -2
        while len(status) < len(data):
            status.append(-2)
            self.logger.warning("Length of status list to short. "
                                "Appending '-2'")
        if len(status) > len(data):
            self.logger.warning("Length of status list to long. ")
        # Try to put to queue
        try:
            self.queue.put([self.name, logtime, data, status])
            self.logger.info("Write to queue (%s)" %
                             str([self.name, logtime, data, status]))
        except Exception as e:
            self.logger.warning("Can not put data to queue (%s), error: %s" % (
                str([self.name, logtime, data, status]), e))
            return -1
        return 0


    def getConfigUpdates(self, name):
        """
        Use this function to get the latest config settings.
        E.g. call this function periodically to check
        if the readoutinterval has changed.
        Returns config as a list.
        """
        try:
            DDB = DobermanDB.DobermanDB(opts, opts.logger)
            config = DDB.getConfig(name)
            if config in [-1, -2, -3]:
                self.logger.error("Unable to get config updates.")
                return -1
            return config[0]
        except Exception as e:
            self.logger.error("Unable to get config updates. Error: %s" % e)
            return -1

if __name__ == '__main__':
    from argparse import ArgumentParser
    import sys
    parser = ArgumentParser(usage='%(prog)s [options] \n\n Doberman: Slow control')

    parser.add_argument("-d", "--debug", dest="loglevel",
                        type=int, help="switch to loglevel debug", default=10)
    opts = parser.parse_args()

    logger = logging.getLogger()
    opts.logger = logger
    if opts.loglevel not in [0, 10, 20, 30, 40, 50]:
        print("ERROR: Given log level %i not allowed. "
              "Fall back to default value of 10" % opts.loglevel)
    logger.setLevel(int(opts.loglevel))
    chlog = logging.StreamHandler()
    chlog.setLevel(int(opts.loglevel))
    formatter = logging.Formatter('%(levelname)s:%(process)d:%(module)s:%'
                                  '(funcName)s:%(lineno)d:%(message)s')
    chlog.setFormatter(formatter)
    logger.addHandler(chlog)

    queue = Queue.Queue(0)
    DoCo = DobermanCommunication(queue, 'the_name', logger)
    print "Testing system by putting two numbers to queue..."
    if DoCo.pushToQueue([55, 46], [3]) != -1:
        print 'In the queue is:', queue.get()
    else:
        print 'Queue empty.'
    print "Testing system by reading config for 'testdev'..."
    print (DoCo.getConfigUpdates('testdev'))
    sys.exit(0)
