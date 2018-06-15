#! /usr/bin/env python3.3

import os
import time
import datetime
import logging
from argparse import ArgumentParser
import threading
import sys
import supervisionWriter
import supervisionComBox



class supervisionMaster(object):
    """
    Class for the supervision plugin master
    """
    def __init__(self, opts, logger):

        self.logger = logger
        self.opts = opts
        
        self._lifes = 99999999999999999999999
        self.supervision_writer = None
        if 'queue' in dir(self.opts):
            if hasattr(self.opts, 'log_path'):
                self.supervision_writer = supervisionWriter.supervisionWriter(self.logger, self.opts.queue, log_path = self.opts.log_path)
            else:
                self.supervision_writer = supervisionWriter.supervisionWriter(self.logger, self.opts.queue)
        else:
            if hasattr(self.opts, 'log_path'):
                self.supervision_writer = supervisionWriter.supervisionWriter(self.logger, None, log_path = self.opts.log_path)
            else:
                self.supervision_writer = supervisionWriter.supervisionWriter(self.logger, None)

        self.super_vision_server = supervisionComBox.supervisionServer(self.logger, (self.opts.server_address,self.opts.server_port))
        self.super_vision_client = supervisionComBox.supervisionClient(self.logger, (self.opts.remote_address,self.opts.remote_port))

        if not 'queue' in dir(self.opts):
            self.logHead()

        self.writerThread = ReadoutThread(self.logger, self.opts, self.supervision_writer, self.super_vision_client)
        self.__super_vision_server_thread = threading.Thread(target=self.super_vision_server.start_server)
        self.__super_vision_server_thread.daemon = True

    def supervisionmaster(self):
        """
        starts the supervision plugin
        """
        self.__super_vision_server_thread.start()
        try:
            self.writerThread.start()
            runner = 0
            while runner < self._lifes:
                runner += 1
                self.logger.info("Main program still alive...")
                if runner%2 == 0:
                    if self.writerThread.stopped or not self.writerThread.isAlive():
                        self.logger.fatal("Logging thread died. Reviving...")
                        self.writerThread.start()
                time.sleep(30)
            self.close()
        except KeyboardInterrupt:
            self.logger.fatal("\n\nProgram killed by ctrl-c\n\n")
            self.close()

    def logHead(self):
        """
        writes the supervision log header to file, containing the connection parameters
        """
        self.supervision_writer.writeToFile(str("# Supervision server running on host: %s : %i (port)."%(self.super_vision_server.get_host(), self.super_vision_server.get_port())))
        self.supervision_writer.writeToFile(str("# Supervising host: %s : %i ."%(self.super_vision_client.get_remote_host(), self.super_vision_client.get_port()))) 
        self.supervision_writer.writeToFile(str("\n\n"))
        self.supervision_writer.writeToFile("^ date (Y-m-d) ^ time (H:M:S) ^ Online status ^ Warning status ^ Alarm status ^")
        return

    def close(self):
        """
        properly closing the supervision plugin
        """
        self.logger.info("Closing the logger")
        self.writerThread.stopped = True
        self.writerThread.Tevent.set()
        self.supervision_writer.close()
        self.super_vision_client.close()
        self.super_vision_server.close()
        return

    def __del__(self):
        self.close()
        return
    
    def __exit__(self):
        self.close()
        return


class ReadoutThread(threading.Thread):
    """
    Class that is the read out thread. Controlls the thread: starting, running and stopping it.
    """
    def __init__(self, logger, opts, writer, super_vision_client):

        self.ReadOutInterval = 30
        self.logger = logger
        self.opts = opts
        self.supervision_writer = writer
        self.super_vision_client = super_vision_client

        if self.opts.loginterval < 1000 and self.opts.loginterval >= 5:
            self.ReadOutInterval = self.opts.loginterval
            self.logger.info("Readout interval set to %i s."%self.ReadOutInterval)
        else:
            self.logger.error("Required readout interval invalid. Running with default 30s.")

        self.stopped = False
        threading.Thread.__init__(self)
        self.Tevent = threading.Event()

    def run(self):
        while not self.stopped:
            self.ReadOutT()
            self.Tevent.wait(self.ReadOutInterval)

    def ReadOutT(self):
        """
        Read out thread itself. Defines the read out format.
        """
        self.logger.debug("Reading data for log...")
        now = datetime.datetime.now()
        #if not self.super_vision_client.
        readout = str("| %s | %s | %s |"%(str(self.super_vision_client.querry_online()), str(self.super_vision_client.querry_warning()), str(self.super_vision_client.querry_alarm())))
        self.supervision_writer.write(readout, now)
        self.logger.info("Logged string: %s"%readout)



if __name__ == '__main__':
    parser = ArgumentParser(usage='%(prog)s [options] \n\n Program to readout the supervision plugin. It opens an own server and reads from time to time from a remote server with a client. So you need:\
    The name and a port under which the server should listen for requests\
    and name and port of a remote supervision server which you want to query for online, warning and alarm status.')
    parser.add_argument("-d", "--debug", dest="loglevel", type=int, help="switch to loglevel debug", default=10)
    parser.add_argument("-i", "--interval", dest="loginterval", type=int, help="logging interval in s, default value: 30 s", default=30)
    parser.add_argument("-r", "--remote", dest="remote_address", type=str, help="remote adress to observe", default="localhost")
    parser.add_argument("-l", "--host", dest="server_address", type=str, help="local adress to listen to (server)", default="localhost")
    parser.add_argument("-p", "--port", dest="server_port", type=int, help="Port to listen to", default=55555)
    parser.add_argument("-o", "--remoteport", dest="remote_port", type=int, help="Remote port to query", default=55555)
    opts = parser.parse_args()
    
    logger = logging.getLogger()
    if not opts.loglevel in [0,10,20,30,40,50]:
        print(("ERROR: Given log level %i not allowed. Fall back to default value of 10"%opts.loglevel))
    logger.setLevel(int(opts.loglevel))

    chlog = logging.StreamHandler()
    chlog.setLevel(int(opts.loglevel))
    formatter = logging.Formatter('%(levelname)s:%(process)d:%(module)s:%(funcName)s:%(lineno)d:%(message)s')
    chlog.setFormatter(formatter)
    logger.addHandler(chlog)

    supervision_master = supervisionMaster(opts, logger)
    supervision_master.supervisionmaster()
    sys.exit(0)
