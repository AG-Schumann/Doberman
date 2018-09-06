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
        details = self.db.readFromDatabase('settings','contacts', {'conn_details' : {'$exists' : 1}}, onlyone=True)['conn_details']
        self.mailconnection_details = details['email']
        self.smsconnection_details = details['sms']
        if not self.mailconnection_details:
            self.logger.critical("No Mail connection details loaded! Will not "
                                 "be able to send warnings and alarms!")
        if not self.smsconnection_details:
            self.logger.critical("No SMS connection details loaded! Will not "
                                 "be able to send alarms by sms!")
    def close(self):
        self.db = None
        return

    def __del__(self):
        self.close()
        return

    def getConnectionDetails(self, which):
        try:
            details = self.db._check('settings','contacts').find_one(
                    {'conn_details' : {'$exists' : 1}})['conn_details']
            if 'mail' in which:
                self.mailconnection_details = details['email']
            else:
                self.smsconnection_details = details['sms']
        except Exception as e:
            self.logger.error('Could not load email connection details!')

    def sendEmail(self, toaddr, subject, message, Cc=None, Bcc=None, add_signature=True):
        '''
        Sends an email. Make sure toaddr is a list of strings.
        '''
        # Get connections details
        if not self.mailconnection_details:
            self.getConnectionDetails('mail')
            if not self.mailconnection_details:
                self.logger.critical("No email connection details loaded! "
                                     "Not able to send warnings and alarms!")
                return -1
        try:
            # Compose connection details and addresses
            now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            server = self.mailconnection_details['server']
            port = int(self.mailconnection_details['port'])
            fromaddr = self.mailconnection_details['fromaddr']
            password = self.mailconnection_details['password']
            if not isinstance(toaddr, list):
                toaddr = toaddr.split(',')
            recipients = toaddr
            try:
                contactaddr = self.mailconnection_details['contactaddr']
            except:
                self.logger.warning("No contact address given. Mail will be "
                                    "sent without contact address.")
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
            self.logger.info("Mail (Subject:%s) sent to %s" %
                             (str(subject), str(toaddr)))
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
        if not self.mailconnection_details:
            self.getConnectionDetails('mail')
            if not self.mailconnection_details:
                self.logger.critical("No email connection details loaded! "
                                     "Not able to send alarms at all!")
                return -1
        if not self.smsconnection_details:
            self.getConnectionDetails('sms')
            if not self.smsconnection_details:
                self.logger.critical("No sms connection details loaded! "
                                     "Not able to send alarms by sms!")
                return -1
        # Compose connection details and addresses
        try:
            server = self.smsconnection_details['server']
            identification = self.smsconnection_details['identification']
            contactaddr = self.smsconnection_details['contactaddr']
            fromaddr = self.mailconnection_details['fromaddr']
            if not phonenumber:
                self.logger.warning("No phonenumber given. "
                                    "Can not send SMS.")
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
            if len(str(message)) > 155:
                self.logger.warning("SMS message exceets limit of 160 "
                                    "characters (%s characters). Message will "
                                    "be cut off." % str(len(str(message))))
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

        # Example from smscreator without email.
        # Direct login.
        '''
        send_ret = ''
        ret_status = False
        sms_recipient = '171xxxxxxxxxx'
        smstext = 'test sms text'

        sms_baseurl = 'https://www.smscreator.de/gateway/Send.asmx/SendSMS'
        sms_user = 'xxxxxxxxxxxxxxxxxxxxxxxxxxxx'
        sms_pass = 'xxxxxxxxxxxxxxxxx'
        sms_caption = 'test'
        sms_sender = '0171xxxxxxxxxxxx'
        sms_type = '6' # standard sms (160 chars): 6

        send_date = time.strftime('%Y-%m-%dT%H:%M:%S')

        request_map = { 'User': sms_user, 'Password': sms_pass, 'Caption' : sms_caption, 'Sender' : sms_sender, 'SMSText' : smstext, 'Recipient' : sms_recipient, 'SmsTyp' : sms_type, 'SendDate' : send_date }
        txdata = urllib.urlencode(request_map)
        txheaders = {}
        try:
            filehandle = urllib2.urlopen(sms_baseurl, txdata)
            send_ret = filehandle.read()
            filehandle.close()
            ret_status = True
        except Exception, e:
            print 'Error happend: %s'%str(e)

        if ret_status:
            print 'Status: SMS to %s send succeeded.' % str(sms_recipient)
        else:
            print 'Status: SMS to %s send failed.' % str(sms_recipient)
        print 'Return data: %s' % str(send_ret)
        '''

def main():
    db = DobermanDB.DobermanDB()
    aldist = alarmDistribution(db)
    msg = 'Something wrong with Doberman? The following things aren\'t heartbeating correctly:\n'
    msg += ' '.join(sys.argv[1:])
    to_addr = [c['email'] for c in db.getContacts('email')]
    aldist.sendEmail(toaddr=to_addr, subject='Doberman heartbeat', message=msg)
    db.close()

if __name__ == '__main__':
    main()
