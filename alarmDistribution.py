import logging
import datetime
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


class alarmDistribution(object):
    """
    Class that sends an email or sms to a given address
    """

    def __init__(self, db):
        """
        Loading connections to Mail and SMS.
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.db = db

    def close(self):
        self.db = None
        return

    def __del__(self):
        self.close()
        return

    def getConnectionDetails(self, which):
        detail_doc = self.db.readFromDatabase('settings','alarm_config',
                {'connection_details' : {'$exists' : 1}}, onlyone=True)
        try:
            return detail_doc[which]
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
            now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            server = connection_details['server']
            port = int(connection_details['port'])
            fromaddr = connection_details['fromaddr']
            password = connection_details['password']
            if not isinstance(toaddr, list):
                toaddr = toaddr.split(',')
            recipients = toaddr
            try:
                contactaddr = connection_details['contactaddr']
            except:
                contactaddr = '--'
            # Compose message
            msg = MIMEMultipart()
            msg['From'] = fromaddr
            msg['To'] = ', '.join(toaddr)
            if Cc:
                if not isinstance(Cc, list):
                    Cc = Cc.split(',')
                msg['Cc'] = ', '.join(Cc)
                recipians = recipients.extend(Cc)
            if Bcc:
                if not isinstance(Bcc, list):
                    Bcc = Bcc.split(',')
                msg['Bcc'] = ', '.join(Bcc)
                recipians = recipients.extend(Bcc)
            msg['Subject'] = subject
            signature = ""
            if add_signature:
                signature = ("\n\n----------\n"
                             "Message created on %s by slowcontrol. "
                             "This is a automatic message. " % now)
                body = str(message) + signature
            else:
                body = str(message)
            msg.attach(MIMEText(body, 'plain'))
            # Connect and send
            if server == 'localhost':  # From localhost
                smtp = smtplib.SMTP(server)
                smtp.sendmail(fromaddr, toaddr, msg.as_string())
            else:  # with e.g. gmail
                server = smtplib.SMTP(server, port)
                server.starttls()
                server.login(fromaddr, password)
                server.sendmail(fromaddr, recipients, msg.as_string())
                server.quit()
            self.logger.info("Mail (Subject:%s) sent" %
                             (str(subject)))
        except Exception as e:
            self.logger.warning("Could not send mail, error: %s." % e)
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
            contactaddr = sconnection_details['contactaddr']
            fromaddr = connection_details['fromaddr']
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
                toaddr = fromaddr
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
            self.logger.error("Could not send sms, error: %s." % e)
            return -1
        return 0

