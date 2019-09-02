import datetime
import smtplib
import Doberman
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
dtnow = datetime.datetime.utcnow

__all__ = 'AlarmMonitor'.split()

class AlarmMonitor(Doberman.Monitor):
    """
    Class that sends monitors for alarms and sends messages
    """

    def Setup(self):
        self.Register(func=self.CheckHeartbeats, period=30, name='heartbeat')
        self.Register(func=self.CheckForAlarms, period=5, name='alarmcheck')

    def getConnectionDetails(self, which):
        detail_doc = self.db.readFromDatabase('settings', 'alarm_config',
                {'connection_details' : {'$exists' : 1}}, onlyone=True)
        try:
            return detail_doc['connection_details'][which]
        except KeyError:
            self.logger.critical('Could not load connection details for %s' % which)
            return None

    def sendEmail(self, toaddr, subject, message, Cc=None, Bcc=None, add_signature=True):
        '''
        Sends an email. Make sure toaddr is a list of strings.
        '''
        # Get connectioins details
        connection_details = self.getConnectionDetails('email')
        if connection_details is None:
            return -1
        try:
            # Compose connection details and addresses
            now = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
            server_addr = connection_details['server']
            port = int(connection_details['port'])
            fromaddr = connection_details['fromaddr']
            password = connection_details['password']
            #self.logger.info(toaddr)
            if not isinstance(toaddr, list):
                toaddr = toaddr.split(',')
            recipients = toaddr
            #self.logger.info(recipients)
            try:
                contactaddr = connection_details['contactaddr']
            except KeyError:
                contactaddr = '--'
            # Compose message
            msg = MIMEMultipart()
            msg['From'] = fromaddr
            msg['To'] = ', '.join(toaddr)
            if Cc:
                if not isinstance(Cc, list):
                    Cc = Cc.split(',')
                msg['Cc'] = ', '.join(Cc)
                recipients.extend(Cc)
            if Bcc:
                if not isinstance(Bcc, list):
                    Bcc = Bcc.split(',')
                msg['Bcc'] = ', '.join(Bcc)
                recipients.extend(Bcc)
            msg['Subject'] = subject
            signature = ""
            if add_signature:
                signature = ("\n\n----------\n"
                             "Message created on %s by slowcontrol. "
                             "This is a automatic message. "
                             % now.isoformat(timespec='minutes'))
                body = str(message) + signature
            else:
                body = str(message)
            msg.attach(MIMEText(body, 'plain'))
            # Connect and send
            if server_addr == 'localhost':  # From localhost
                smtp = smtplib.SMTP(server_addr)
                smtp.sendmail(fromaddr, toaddr, msg.as_string())
            else:  # with e.g. gmail
                server = smtplib.SMTP(server_addr, port)
                server.starttls()
                server.login(fromaddr, password)
                server.sendmail(fromaddr, recipients, msg.as_string())
                server.quit()
            self.logger.info("Mail (Subject:%s) sent" % (str(subject)))
        except Exception as e:
            self.logger.warning("Could not send mail, error: %s (%s)." % (str(e), type(e)))
            try:
                server.quit()
            except:
                pass
            return -1
        return 0

    def sendSMS(self, phonenumber, message):
        '''
        Sends an SMS.
        This works with sms sides which provieds sms sending by email.
        '''
        # Get connection details
        connection_details = self.getConnectionDetails('sms')
        if connection_details is None:
            return -1
        # Compose connection details and addresses
        try:
            server = connection_details['server']
            identification = connection_details['identification']
            contactaddr = connection_details['contactaddr']
            #fromaddr = connection_details['fromaddr']
            if not phonenumber:
                self.logger.warning("No phonenumber given. "
                                    "Can not send SMS.")
                return 0
            # Server has different type request for 1 or several numbers.
            elif len(phonenumber) == 1:
                toaddr = str(identification) + '.' + \
                    phonenumber[0] + '@' + str(server)
                Bcc = None
            elif len(phonenumber) > 1:
                toaddr = contactaddr
                Bcc = [str(identification) + '.' + str(number) +
                       '@' + str(server) for number in phonenumber]
            message = str(message)
            subject = ''
            # Long SMS (>160 characters) cost more and are shortened
            if len(message) > 155:
                self.logger.warning("SMS message exceets limit of 160 "
                                    "characters (%s characters). Message will "
                                    "be cut off." % str(len(message)))
                message = message[:155]
            Cc = None
            if self.sendEmail(toaddr=toaddr,
                              subject=subject,
                              message=message,
                              Cc=Cc, Bcc=Bcc,
                              add_signature=False) == -1:
                self.logger.error("Could not send SMS! "
                                  "Email to SMS not working.")
                return -1

        except Exception as e:
            self.logger.error("Could not send sms, error: %s (%s)." % (e, type(e)))
            return -1
        return 0

    def CheckForAlarms(self):
        doc_filter = {'acknowledged' : {'$exists' : 0}}
        messages = {}
        msg_format = '{name} : {when} : {msg}'
        updates = {'$set' : {'acknowledged' : dtnow()}}
        db_col = ('logging', 'alarm_history')
        if self.db.Count(*db_col, doc_filter) == 0:
            return
        for doc in self.db.readFromDatabase(*db_col, doc_filter, sort=[('howbad', -1)]):
            howbad = int(doc['howbad'])
            if (howbad,) not in messages:
                messages[(howbad,)] = []
            self.db.updateDatabase(*db_col, {'_id' : doc['_id']}, updates)
            messages[(howbad,)].append(doc)
        if messages:
            self.logger.warning(f'Found alarms!')
            for (lvl,), msg_docs in messages.items():
                message = '\n'.join(map(lambda d :
                    msg_format.format(**d, when=d['_id'].generation_time), msg_docs))
                self.sendMessage(lvl, message)
        return

    def sendMessage(self, level, message):
        """
        Sends 'message' to the contacts specified by 'level'
        """
        now = dtnow()
        message_time = self.db.GetRunmodeDetail(runmode='default',
                fieldname='message_time')
        if hasattr(self, 'last_message_time') and self.last_message_time is not None:
            dt = (now - self.last_message_time).total_seconds()/60
            if dt < message_time:
                self.logger.warning('Sent a message too recently (%i minutes), '
                    'message timer at %i' % (dt, message_time))
                return -3

        for prot, recipients in self.db.getContactAddresses(level).items():
            if prot == 'sms':
                if self.sendSMS(recipients, message) == -1:
                    self.logger.error('Could not send SMS')
                    return -4
            elif prot == 'email':
                subject = 'Doberman alarm level %i' % level
                if self.sendEmail(toaddr=recipients, subject=subject,
                                         message=message) == -1:
                    self.logger.error('Could not send email!')
                    return -5
            self.last_message_time = now
        return 0

    def CheckHeartbeats(self):
        hosts = self.db.readFromDatabase('settings', 'hosts',
                {'status' : {'$ne' : 'offline'}})
        now = dtnow()
        for host in hosts:
            if (now - host['heartbeat']).total_seconds() > 3*utils.heartbeat_timer:
                alarm_doc = {'name' : 'alarm_monitor', 'howbad' : 0,
                    'msg' : 'Host "%s" hasn\'t heartbeated recently' % host['hostname']}
                self.db.logAlarm(alarm_doc)
