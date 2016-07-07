#! /usr/bin/env python3.3

import socket
import sys
import time
import ssl
import errno
import select
import logging
from argparse import ArgumentParser
from supervisionCommand import supervisionProtocol
from ast import literal_eval
from collections import deque

RECV_BUFFER = 32                            #defines the bytes that will always be sent or read
DELIMITER = b"\k"                           #defines a line delimiter - seams that things like \0 don't work verry well
PORTRANGE = (15000,65535)                   #if the program does not get a port, it tries one from the given ports
DEFAULT_TIMEOUT = 5                         #time out until the connection dies
CERTFILE = "server.crt"                     #server cert file for the ssl connection
KEYFILE = "server.key"                      #key file for the ssl connection

class supervision(object):
    """
    supervision base class. Do not call itself. Does only provide generally needed functions and methods
    """
    def __init__(self, logger, **kwds):
        self.logger = logger

        if 'DEFAULT_TIMEOUT' in kwds.keys():
            DEFAULT_TIMEOUT = float(kwds['DEFAULT_TIMEOUT'])
            self.logger.info("Changed the default timeout to %i."%DEFAULT_TIMEOUT)
        if 'PORTRANGE' in kwds.keys():
            try:
                kwds['PORTRANGE'] = literal_eval(kwds['PORTRANGE'])
                if (isinstance(kwds['PORTRANGE'], tuple) or isinstance(kwds['PORTRANGE'], list)) and len(kwds['PORTRANGE']) == 2:
                    PORTRANGE = (int(kwds['PORTRANGE'][0]), int(kwds['PORTRANGE'][1]))
                    self.logger.info("Changed the default timeout to %s."%str(PORTRANGE))
            except:
                pass
        
        if 'CERTFILE' in kwds.keys():
            try:
                kwds['CERTFILE'] = literal_eval(kwds['CERTFILE'])
                if isinstance(kwds['CERTFILE'], str):
                    CERTFILE = str(kwds['CERTFILE'])
                    self.logger.info("Changed the default certificate file path to: %s."%CERTFILE)
            except:
                pass

        if 'KEYFILE' in kwds.keys():
            try:
                kwds['KEYFILE'] = literal_eval(kwds['KEYFILE'])
                if isinstance(kwds['KEYFILE'], str):
                    KEYFILE = str(kwds['KEYFILE'])
                    self.logger.info("Changed the default certificate file path to: %s."%KEYFILE)

            except:
                pass

    def __exit__(self):
        self.close()

    def close(self):
        print "wrong way \n\n\n\n\n"
        pass

    def _interpr_(self, mes):
        """
        helper function to clean a incoming message
        """
        mes = bytes(mes)
        mes = mes.lstrip().rstrip()
        if mes == b'0':
            return False
        mes = mes.lstrip(b'0')
        return mes


class supervisionClient(supervisionProtocol, supervision):
    """
    Client class for the supervision client. It can send messages over a ssl secured connection to a server. The sslsocket has to be given as tuple (hostname, port).
    """
    def __init__(self, logger, sslsocket, **kwds):
        super(supervisionClient, self).__init__()        
        super(supervisionClient, self).__init__(**kwds)
        self.logger = logger
        self.__ssl_context = None
        self.__inbuffer = deque()
        self.__outbuffer = ''
#TODO: check status implementation - isn't done clean yet
        self.status = 0 # 0: allright, -1, nothing recived, 1: received, 2: send, -2: not sent
        self.__port = sslsocket[1]
        self.__connected_host = sslsocket[0]
        self.__restart_client = True
        self.__redo_counter = 0


        self.hostname = ''
        self.__online = False
        self.__sock = None
        self.__sslsocket = None
        self.__server_cert = None
        try:
            self.logger.debug("Generating ssl context...")
            self.__ssl_context = ssl.create_default_context(purpose=Purpose.SERVER_AUTH)
#        self.__ssl_context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
            self.__ssl_context.verify_mode = ssl.CERT_REQUIRED
            self.__ssl_context.check_hostname = True
#            self.__ssl_context.load_verify_locations("/etc/ssl/certs/ca-bundle.crt")
            self.__ssl_context.load_cert_chain(certfile=CERTFILE, keyfile=KEYFILE)            
        except AttributeError:
            pass
        #self.__run_socket()

    def get_remote_host(self):
        """
        returns the target, so sever host name
        """
        self.logger.info("The client will connect to the host: %s"%self.__connected_host)
        return self.__connected_host

    def get_port(self):
        """
        returns the port where the server is expected to run
        """
        self.logger.info("The client will connect on port: %s"%self.__port)
        return self.__port
    
    def __run_socket(self):
        """
        starts the socket connection, wraps the ssl layer on it
        """
        #TODO : take logger messages out and implement them in not __ private functions basing on status codes
        self.__sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.__sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.logger.info("Starting client...")
        try:
            self.__sock.connect((self.__connected_host, self.__port))
        except socket.error, error:
            self.logger.warning("Connection error: %s."%str(error))
            if error.errno == 111:
                self.status = -1
            else:
                raise error
            return False
        self.__sock.setblocking(0)
        self.__sock.settimeout(DEFAULT_TIMEOUT)
        if not self.__ssl_context is None:
            self.__sslsocket = self.__ssl_context.wrap_socket(self.__sock, server_hostname=self.__connected_host,cert_reqs=ssl.CERT_REQUIRED,ca_certs=CERTFILE)
        else:
            self.__sslsocket = ssl.wrap_socket(self.__sock,ca_certs=CERTFILE,cert_reqs=ssl.CERT_REQUIRED)
        self.__server_cert = self.__sslsocket.getpeercert()
        self.logger.info("Successfully connected - peer cipher is: %s"%str(self.__sslsocket.cipher()))
        if not self.check_cert():
            self.logger.fatal("cannot verify server cerificate! Stopped.")
            self.__online = False
            self.__status = -3
            self.close()
        while True:
            try:
                self.logger.debug("Doing ssl handshake")
                self.__sslsocket.do_handshake()
                break
            except ssl.SSLWantReadError:
                select.select([self.__sslsocket], [], [])
            except ssl.SSLWantWriteError:
                select.select([], [self.__sslsocket], [])
        self.__redo_counter = 0
        self.__inbuffer = deque()
        self.__outbuffer = ''
        self.status = 0
        self.__online = True
        self.logger.debug("Being online now.")
    
    def check_cert(self):
        """
        checks whether the server cert goes well with the server. Has an implementation weakness: right now no server certificate field commonName might appear, so the connected hostname is never checked
        """
        if self.__server_cert is None:
            self.__server_cert = self.__sslsocket.getpeercert()
        self.logger.debug("The server which is connected delivered the following certificat: %s"%str( self.__server_cert))
        try:
            ssl.match_hostname(self.__server_cert, self.__sslsocket.getpeername()[0])
        except ssl.CertificateError:
            self.logger.fatal("Detected bad certificate of peered server. Stopped!")
            return False
        for field in self.__server_cert['subject']:
# TODO: there might be no commonName, improve the cert check procedure!
            if field[0][0] == 'commonName':
                certhost = field[0][1]
                if certhost != self.__connected_host:
                    raise ssl.SSLError("Host name '%s' doesn't match certificate host '%s'"%(self.__connected_host, certhost))
        return True

    def restart_client(self):
        """
        restart the client. Is automatically done if restart client is set to true. Note that the manual restarting of a connection might lead to loss of information between client and server
        """
        self.logger.debug("Restarting client. Auto restart is set to:%s."%str(self.__restart_client))
        if not self.__sslsocket is None:
            try:
                self.__sslsocket.shutdown(socket.SHUT_RDWR)
            except socket.error, err:
                if not err.errno == 9:
                    raise err
                self.logger.debug("Client connection was already shut down.")
                self.status = -1
            self.__sslsocket.close()
            self.__sock = None
        if not self.__sock is None:
            try:
                self.__sock.shutdown(socket.SHUT_RDWR)
                self.__sock.close()
                self.__online = False
            except socket.error, error:
                if error.errno == 107:
                    self.status = -1
                self.logger.debug("Client connection was already shut down.")                
        self.__run_socket()
        
    def mod_socket(self, sslsocket):
        """
        connect to another socket. All queued values and secrets will be gone afterwards
        """
        self.logger.warning("Connecting to another server: %s"%str(sslsocket))
        self.__init__(sslsocket)
    
    def send(self, message):
        """
        send a message to the connected server. Expects that the server can react on this message - gets the answer of the server on this question, checks it, evaluates it and returns the resulting value. For possibles messages see supervisionCommand
        """
        if self.__restart_client:
            self.restart_client()
        check = ''
        answer = ''
        while self.__redo_counter <= 5 and not answer:
            self.logger.debug("Trying to send a message.")
            answer = self._send(message)
        check = self.check_reply(message, answer)
        self.logger.info("Got an answer: %s."%str(check))
        if check < 0:
            self.__redo_counter = 6
            check = -1
        else:
            if check == 0:
                self.logger.info("Resending message...")
                return self.send(message)
            else:
                self.logger.debug("Reseting sender counter.")
                self.__redo_counter = 0
        if self.__restart_client:
            if not self.__sslsocket is None:
                try:
                    self.__sslsocket.shutdown(socket.SHUT_RDWR)
                    self.__sslsocket.close()
                    self.__online = False
                except socket.error, error:
                    if error.errno == 107:
                        self.status = -1
        return check

    def _send(self, message):
        """
        technically sending a message. Can send raw messages
        """
        if len(str(message)) >= 5:
            self.logger.warning("Message to sent is too long. Aborted.")
            return False
        if not isinstance(message, int) and not isinstance(message, str):
            self.logger.warning("Message to sent is no string or integer. Aborted.")
            return False
        if self.__redo_counter > 5:
            self.status = -2
            self.logger.warning("Sending failed: tried too often. Aborting.")
            return False
        message = str(message)+DELIMITER
        self.__outbuffer = message
        answer = ''
        self.logger.debug("Sending...")
        while len(message) and self.__redo_counter <= 5:
            self.__redo_counter += 1
            while True:
                try:
                    self.logger.debug("Sending message: %s."%str(message))
                    sent = self.__sslsocket.send(message)
                    message = message[sent:]
                except socket.error, error:
                    self.logger.warning("Socket error, error code: %i."%error.errno)
                    self.status = -3
                    if error.errno != errno.EAGAIN:
                        self.logger.warning("Skipping resending.")
                        break
                    else:
                        self.logger.info("Resending...")
                    select.select([], [self.__sslsocket], [])
                except ssl.SSL_ERROR_WANT_WRITE:
                    select.select([], [self.__sslsocket], [])
                finally:
                    self.logger.debug("Reading answer...")
                    self.__read()
                    if len(self.__inbuffer) == 0:
                        self.logger.info("Got no answer - resending")
                        message = self.__outbuffer
                        self.__inbuffer = deque()
                        self.status = -1
                        return False
                    iread = self._interpr_(self.__inbuffer.popleft())
                    if b'A' in iread:
                        if len(self.__inbuffer) < 1:
                            self.__read()
                        answer = self._interpr_(self.__inbuffer.popleft())
                        break                        
                    else:
                        self.logger.info("Cannot interprete message, resending.")
                        message = self.__outbuffer
                        self.__inbuffer = deque()
                        self.status = -1
                        return False
            if self.status == -3:
                continue
        self.logger.info("Successfully send and received as answer: %s."%str(answer))
        self.status = 2
        return answer

    def __read(self):
        """
        reads informations from the connected server
        """
        #TODO : take logger messages out and implement them in not __ private functions basing on status codes
        rec_bytes = 0
        message = ''
        self.logger.debug("Reading...")
        if self.status < 0 or not self.__online:
            self.logger.warning("Cannot read - status is offline!")
            return False
        while rec_bytes < RECV_BUFFER:
            data = None
            try:
                data = bytes(self.__sslsocket.recv(min(RECV_BUFFER-rec_bytes, RECV_BUFFER)))
            except socket.timeout:
                self.logger.warning("Got a time out. Time out is set to: %s."%str(self.__sslsock.gettimeout()))
                if not data == '':
                    break
                else:
                    self.logger.debug("Received no data...")
                    break
            except ssl.SSL_ERROR_WANT_READ:
                select.select([self.__sslsocket], [], [])
            if data == '':
                self.status = -1
                self.__redo_counter += 1
                if self.__redo_counter <= 5:
                    self.logger.info("Connection might be broken... Waiting before retrying.")
                    self.status = -1
                    time.sleep(5)
                    continue
                else:
                    self.status = -1
                    self.logger.warning("Connection is broken... Restarting connection.")
                    self.restart_client()
            message = bytes(message + data)
            if message.endswith(DELIMITER):
                self.__redo_counter = 0
                message = message[:len(message)-len(DELIMITER)]
                break
        else:
            self.logger.warning("Reading error - got too much data. Aborted")
            self.status = -1
            return False
        if message != '':
                self.logger.debug("Pushing data to input buffer: %s."%str(message.split(bytes(DELIMITER))))
                self.__inbuffer += deque(message.split(bytes(DELIMITER)))
        self.status = 1
        self.__redo_counter = 0
        return True
    
    def close(self):
        """
        properly destroy and close the connection
        """
        if not self.__ssl_context is None:
            del(self.__ssl_context)
        #del(self.__inbuffer, self.__outbuffer)
        if not self.__sslsocket is None:
            try:
                self.__sslsocket.shutdown(socket.SHUT_RDWR)
                self.__sock = None
            except socket.error, err:
                if not err.errno == 9:
                    raise err
            self.__sslsocket.close()
        if not self.__sock is None:
            try:
                self.__sock.shutdown(socket.SHUT_RDWR)
            except socket.error, err:
                if err.errno != 9 and err.errno != 107:
                    raise err
            self.__sock.close()
            self.__online = False


class supervisionServer(supervisionProtocol, supervision):
    """
    Server for the supervision plugin. Needs a sslsocket (('hostname', port)) to listen to
    """
    def __init__(self, logger, sslsocket, **kwds):
        super(supervisionServer, self).__init__()
        super(supervisionServer, self).__init__(**kwds)
        self.logger = logger
        self.__ssl_context = None
        self.__inbuffer = deque()
        self.__outbuffer = ''
#TODO: check status implementation - isn't done clean yet
        self.status = 0 # 0: allright, -1, nothing recived, 1: received, 2: send, -2: not sent
        self.__port = sslsocket[1]
        self.__connected_host = sslsocket[0]
        self.__restart_client = True

        self.__ssl_context = None
        self.__inbuffer = deque()
        self.__outbuffer = ''
#TODO: check status implementation - isn't done clean yet
        self.status = 0 # 0: allright, -1, nothing recived, 1: received, 2: send, -2: not sent
        self.__sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.__sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.__sock.setblocking(True)
        self.__port = sslsocket[1]
        self.hostname = sslsocket[0]


        try:
            self.logger.debug("Trying to initiate ssl context...")
            self.__ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            self.__ssl_context.load_cert_chain(certfile=CERTFILE, keyfile=KEYFILE)
            self.__ssl_context.verify_mode = ssl.CERT_REQUIRED
            self.__ssl_context.check_hostname = True
            self.__ssl_context.load_verify_locations("/etc/ssl/certs/ca-bundle.crt")
        except AttributeError:
            pass
        finally:
            self.logger.debug("Successfully initiated ssl context.")
 
    def get_host(self):
        """
        returns the hostname to which the server is bind
        """
        self.logger.info("The hostname the server is listening to is: %s."%self.hostname)
        return self.hostname

    def get_port(self):
        """
        returns the port on which the server is listening
        """
        self.logger.info("The port on which the server is listening is: %i."%self.__port)
        return self.__port

    def mod_socket(self, sslsocket):
        """
        use this if you want to run the server on another hostname or port. sslsocket has to be a tuple: ("hostname", port)
        """
        self.logger.debug("Changing the server to (name, port):%s."%str(sslsocket))
        self.__init__(sslsocket)

    def start_server(self):
        """
        start the server. This is not done automatically.
        """
        """
serversocket.bind((socket.gethostname(), 14525))
---------------------------------------------------------------------------
error                                     Traceback (most recent call last)
<ipython-input-4-51ca638910d9> in <module>()
----> 1 serversocket.bind((socket.gethostname(), 14525))

/usr/lib/python2.7/socket.pyc in meth(name, self, *args)
    222 
    223 def meth(name,self,*args):
--> 224     return getattr(self.__sock,name)(*args)
    225 
    226 for _m in __socketmethods:

error: [Errno 98] Address already in use

In [5]: try:
   ...:     serversocket.bind((socket.gethostname(), 14525))
   ...: except IOError, err:
   ...:     if err.errno == 98:
   ...:         print 'ooo'
   ...:     else:
   ...:         print err.errno
   ...:         raise
   ...:     
ooo
        """
        self.logger.debug("Trying to start the server...")
        tmphostname = ''
        if self.hostname == '':
            self.logger.info("No host name was given. Used automatically: %s"%socket.gethostname())
            tmphostname = socket.gethostname()
        self.__sock.bind((tmphostname, self.__port))
        self.__sock.listen(5)
        self.logger.debug("Listening now as server...")
        self.__inbuffer = deque()
        try:
            while True:
                connection, clientaddress = self.__sock.accept()
                sslconnection = None
                if not self.__ssl_context is None:
                    sslconnection = self.__ssl_context.wrap_socket(connection, server_side=True)
                else:
                    sslconnection = ssl.wrap_socket(connection, server_side=True, certfile=CERTFILE,keyfile=KEYFILE)
                self.logger.info("Accepted a connection from %s"%repr(clientaddress))
                self.__read(sslconnection)
        except KeyboardInterrupt:
            self.logger.fatal("\n\nProgram killed by ctrl-c\n\n")
            self.close()
    def __send(self, message, sock = None):
        """
        send a message over sock (has to be a socket). If none is given the standard socket is used. This might fail if the standard socket is already listening
        """
        #TODO : take logger messages out and implement them in not __ private functions basing on status codes
        if sock is None:
            sock = self.__sock
        if len(str(message)) >= 5:
            self.logger.warning("The message to sent was too long. Skipped sending!")
            return False
        if not isinstance(message, int) and not isinstance(message, str):
            self.logger.warning("The message to sent was not int or string. Skipped sending!")
            return False
        message = str(message)+DELIMITER
        while len(message):
            try:
                self.logger.debug("Going to send: %s."%repr(message))
                sent = sock.send(message)
                message = message[sent:]
                if len(message):
                    self.logger.debug("Still left to send: %s."%message)
            except socket.error, error:#  ssl.SSLWantWriteError: ?
                self.logger.warning("Have not sent %s, because of error: %s with error code: %s"%(message, str(error),  str(error.errno)))
                self.status = -2
                if error.errno != errno.EAGAIN:
                    raise error
                self.logger.info("Trying again...")
                select.select([], [sock], [])
        self.logger.debug("Successfully sent.")
        self.status = 2
        return True

    def __read(self, connection = None):
        """
        reads something from a connection and returns it
        """
        #TODO : take logger messages out and implement them in not __ private functions basing on status codes
        rec_bytes = 0
        message = ''
        if connection is None:
            con, clientaddress = self.__sock.accept()
            self.logger.debug("No connection to read from given, choosing one automatically from %s..."%str(clientaddress))
            if not self.__ssl_context is None:
                connection = self.__ssl_context.wrap_socket(con, server_side=True)
            else:
                connection = ssl.wrap_socket(con, server_side=True)

        connection.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        connection.setblocking(True)
        connection.settimeout(DEFAULT_TIMEOUT)
        self.logger.debug("Starting to read...")        
        try:
            while rec_bytes < RECV_BUFFER:
                data = ''
                try:
                    data = bytes(connection.recv(min(RECV_BUFFER-rec_bytes, RECV_BUFFER)))
                    self.logger.debug("Received data: %s."%data)
                except socket.timeout:
                    self.logger.warning("Receiving data timed out...")
                    if not data == '':
                        pass
                    else:
                        self.logger.warning("Received no data so far")
                        pass
                if data == '':
                    self.status = -1
                    self.logger.warning("Received no data so far - connection might be broken?")
                    break
                    #raise RuntimeError("socket connection broken")
                message = bytes(message + data)
                if message.endswith(DELIMITER):
                    message = message[:len(message)-len(DELIMITER)]
                    break
            else:
                self.status = -1
                self.logger.warning("Reading data failed. Got too much input data. Rejected.")
                return False
            if message != '':
                self.logger.debug("Pushing data to input buffer: %s."%str(message.split(bytes(DELIMITER))))
                self.__inbuffer += deque(message.split(bytes(DELIMITER)))
        finally:
            #if len(self.__inbuffer) > 0:
            while len(self.__inbuffer):
                self.logger.info("ACK the incoming message.")
                self.__send('A', connection)
                message = self._interpr_(self.__inbuffer.pop())
                if message:
                    self.logger.info("Replying on request: %s"%str(self.reply(message)))
                    self.__send(self.reply(message), connection)
                else:
                    continue
                self.status = 1
            else:
                self.status = -1
            try:
                self.logger.debug("Closing input connection")
                connection.shutdown(socket.SHUT_RDWR)
                connection.close()
            except IOError, err:
                if err.errno == 107:
                    connection.close()
        return True

    def close(self):
        """
        close the server properly
        """
        if not self.__ssl_context is None:
            del(self.__ssl_context)
#        del(self.__inbuffer, self.__outbuffer)
        
        if not self.__sock is None:
            try:
                self.__sock.shutdown(socket.SHUT_RDWR)
            except socket.error, err:
                if err.errno == 107:
                    pass
                else:
                    raise err
            self.__sock.close()
            self.__sock = None


if __name__ == '__main__':
    parser = ArgumentParser(usage='%(prog)s [options] \n\n Program to run the supervision server or client.  It can open an own server or read from a remote server with a client. So you might need:\
    The name and a port under which the server should listen for requests\
    and name and port of a remote supervision server which you want to query for online, warning and alarm status.')
    parser.add_argument("-d", "--debug", dest="loglevel", type=int, help="switch to loglevel debug", default=10)
    parser.add_argument("-a", "--address", dest="address", type=str, help="address to listen to or to send to", default='localhost')
    parser.add_argument("-p", "--port", dest="port", type=int, help="Target port or port to listen on", default=55555)
    parser.add_argument("-s", "--server", dest="server", type=bool, help="Become the server", default=False)
    parser.add_argument("-c", "--client", dest="client", type=bool, help="Become the client", default=True)
    parser.add_argument("-m", "--message", dest="message", type=str, help="Send a message as client. Up to 3 symbols")
    opts = parser.parse_args()
    
    logger = logging.getLogger()
    if not opts.loglevel in [0,10,20,30,40,50]:
        print("ERROR: Given log level %i not allowed. Fall back to default value of 10"%opts.loglevel)
    logger.setLevel(int(opts.loglevel))

    chlog = logging.StreamHandler()
    chlog.setLevel(int(opts.loglevel))
    formatter = logging.Formatter('%(levelname)s:%(process)d:%(module)s:%(funcName)s:%(lineno)d:%(message)s')
    chlog.setFormatter(formatter)
    logger.addHandler(chlog)
    if opts.server:
        opts.client = False
    if (opts.server and opts.client) or (not opts.server and not opts.client):
        print 'can only server or client. You have to choose one'
        sys.exit(-1)
    if opts.server:
        server = supervisionServer(logger, (opts.address, opts.port))
        server.start_server()
    else:
        #for i in range(1,1000000):
        for i in range(1,2):
            client = supervisionClient(logger, (opts.address, opts.port))
            if opts.message:
                print 'wanna send', opts.message
                client.send(opts.message)
            else:
                print "online:", client.querry_online(), "\n --------------------------"
                client.close()
                client = supervisionClient(logger, (opts.address, opts.port))
                print "warning:", client.querry_warning(), "\n --------------------------"
                client.close()
                client = supervisionClient(logger, (opts.address, opts.port))
                print "alarm:", client.querry_alarm(), "\n --------------------------"
    sys.exit(0)
