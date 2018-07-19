#!/usr/bin/env python3
import sys
from argparse import ArgumentParser
import logging
import datetime
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


class alarmDistribution(object):
    """
    Class that sends an email or to a given address
    """

    def __init__(self, opts):
        """
        Loading connections to Mail and SMS.
        """
        self.logger = logging.getLogger(__name__)
        self.mailconnection_details = self.getMailConnectionDetails()
        self.smsconnection_details = self.getSMSConnectionDetails()
        if not self.mailconnection_details:
            self.logger.critical("No Mail connection details loaded! Will not "
                                 "be able to send warnings and alarms!")
        if not self.smsconnection_details:
            self.logger.critical("No SMS connection details loaded! Will not "
                                 "be able to send alarms by sms!")

    def getMailConnectionDetails(self):
        """
        Reading file Mail_connectiondetail.txt and returning entries.
        Should be saved in the order:
          'server','port','fromaddr','password','contactaddr'
        """
        try:
            connection_details = []
            with open("settings/Mail_connectiondetails.txt", "r") as f:
                for line in f:
                    if not line or line == '\n':
                        continue
                    if str(line)[0] == '#':
                        continue
                    line = line.split('=')
                    connection_details.append(line[1].strip())
        except Exception as e:
            self.logger.warning("Can not load email connection details. "
                                "Error: %s" % e)
            return []
        # Protection against default connection details
        if connection_details[2] == "myemail@gmail.com":
            self.logger.error("Default identification in file "
                              "Mail_connectiondetails.txt! No alarms will "
                              "be sent. Update connectiondetails first!")
            return []
        self.logger.debug("Email connection details loaded from file.")
        return connection_details

    def getSMSConnectionDetails(self):
        """
        Reading file SMS_connectiondetail.txt and returning entries.
        """
        try:
            connection_details = []
            with open("settings/SMS_connectiondetails.txt", "r") as f:
                for line in f:
                    if not line or line == '\n':
                        continue
                    if str(line)[0] == '#':
                        continue
                    line = line.split('=')
                    connection_details.append(line[1].strip())
        except Exception as e:
            self.logger.warning("Can not load SMS connection details. "
                                "Error: %s" % e)
            return []
        # Protection against default connection details
        if connection_details[1] == "myserialnumber.mypassword":
            self.logger.error("Default identification in file "
                              "SMS_connectiondetails.txt! No SMS will be "
                              "sent. Update connectiondetails first!")
            return []
        self.logger.debug("SMS connection details loaded from file.")
        return connection_details

    def sendEmail(self, toaddr, subject, message, Cc=None, Bcc=None, add_signature=True):
        '''
        Sends an email. Make sure toaddr is a list of strings.
        '''
        # Get connections details
        if not self.mailconnection_details:
            self.getMailConnectionDetails()
            if not self.mailconnection_details:
                self.logger.critical("No email connection details loaded! "
                                     "Not able to send warnings and alarms!")
                return -1
        try:
            # Compose connection details and addresses
            now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            server = self.mailconnection_details[0]
            port = int(self.mailconnection_details[1])
            fromaddr = self.mailconnection_details[2]
            password = self.mailconnection_details[3]
            if not isinstance(toaddr, list):
                toaddr = toaddr.split(',')
            recipients = toaddr
            try:
                contactaddr = self.mailconnection_details[4]
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
            contactaddr_cond1 = len(contactaddr) > 3
            contactaddr_cond2 = False  # Test if contactaddr is a mail address
            if len(contactaddr.split("@")) == 2:
                if len(contactaddr.split("@")[1].split(".")) >= 2:
                    contactaddr_cond2 = True
            if contactaddr_cond2:
                msg.add_header('reply-to', contactaddr)
            signature = ""
            if add_signature:
                signature = ("\n\n----------\n"
                             "Message created on %s by slowcontrol. "
                             "This is a automatic message. " % now)
                if contactaddr_cond2:
                    signature += ("Reply for further informations or questions"
                                  " (Replies are sent to '%s'.)" % contactaddr)
                elif contactaddr_cond1:
                    signature += ("Do not reply. Contact '%s' for further "
                                  "informations or questions." % contactaddr)
                else:
                    signature += ("Do not reply.")
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
            self.getMailConnectionDetails()
            if not self.mailconnection_details:
                self.logger.critical("No email connection details loaded! "
                                     "Not able to send alarms at all!")
                return -1
        if not self.smsconnection_details:
            self.getSMSConnectionDetails()
            if not self.smsconnection_details:
                self.logger.critical("No sms connection details loaded! "
                                     "Not able to send alarms by sms!")
                return -1
        # Compose connection details and addresses
        try:
            server = self.smsconnection_details[0]
            identification = self.smsconnection_details[1]
            contactaddr = self.smsconnection_details[2]
            fromaddr = self.mailconnection_details[2]
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
            elif len(str(message)) < 105:
                message = message + "--Automatic SMS. Help conctact: %s." % contactaddr
            elif len(str(message)) < 140:
                message = message + "--Automatic SMS."
                self.logger.warning("Could not add contact address as message "
                                    "would exceet limit of 160 characters.")
            else:
                self.logger.warning("Could not add 'Automatic message' and "
                                    "contact address as message would exceet "
                                    "limit of 160 characters.")
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

