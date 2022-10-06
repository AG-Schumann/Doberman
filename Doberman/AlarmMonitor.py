import time
import requests
import json
import smtplib
from datetime import timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import Doberman

dtnow = Doberman.utils.dtnow

__all__ = 'AlarmMonitor'.split()


class AlarmMonitor(Doberman.PipelineMonitor):
    """
    Class that monitors for alarms and sends messages
    """

    def setup(self):
        super().setup()
        self.current_shifters = self.db.distinct('contacts', 'name', {'on_shift': True})
        self.current_shifters.sort()
        self.register(obj=self.check_shifters, period=60, name='shiftercheck', _no_stop=True)

    def get_connection_details(self, which):
        detail_doc = self.db.get_experiment_config('alarm')
        try:
            return detail_doc['connection_details'][which]
        except KeyError:
            self.logger.critical(f'Could not load connection details for {which}')
            return None

    def send_phonecall(self, phone_numbers, message):
        # Get connection details
        connection_details = self.get_connection_details('twilio')
        if connection_details is None:
            raise KeyError("No connection details obtained from database.")
        # Compose connection details and addresses
        url = connection_details['url']
        fromnumber = connection_details['fromnumber']
        auth = tuple(connection_details['auth'])
        maxmessagelength = int(connection_details['maxmessagelength'])

        if not phone_numbers:
            raise ValueError("No phone number given.")

        message = str(message)
        # Long messages are shortened to avoid excessive fees
        if len(message) > maxmessagelength:
            message = ' '.join(message[:maxmessagelength + 1].split(' ')[0:-1])
            message = '<p>' + message + '</p>'
            message += '<p>Message shortened.</p>'
            self.logger.warning(f"Message exceeds {maxmessagelength} "
                                "characters. Message will be shortened.")
        message = f"This is the {self.db.experiment_name} alarm system. " + message
        if isinstance(phone_numbers, str):
            phone_numbers = [phone_numbers]
        for tonumber in phone_numbers:
            data = {
                'To': tonumber,
                'From': fromnumber,
                'Parameters': json.dumps({'message': message})
            }
            self.logger.warning(f'Making phone call to {tonumber}')
            response = requests.post(url, auth=auth, data=data)
            if response.status_code != 201:
                self.logger.error(f"Couldn't place call, status"
                                  + f" {response.status_code}: {response.json()['message']}")

    def send_email(self, toaddr, subject, message, cc=None, bcc=None, add_signature=True):

        # Get connection details
        connection_details = self.get_connection_details('email')
        if connection_details is None:
            return -1
        try:
            # Compose connection details and addresses
            now = dtnow().replace(tzinfo=timezone.utc).astimezone(tz=None).strftime("%Y-%m-%d %H:%M %Z")
            server_addr = connection_details['server']
            port = int(connection_details['port'])
            fromaddr = connection_details['fromaddr']
            password = connection_details['password']
            if not isinstance(toaddr, list):
                toaddr = toaddr.split(',')
            recipients = toaddr
            msg = MIMEMultipart()
            msg['From'] = fromaddr
            msg['To'] = ', '.join(toaddr)
            if cc:
                if not isinstance(cc, list):
                    cc = cc.split(',')
                msg['Cc'] = ', '.join(cc)
                recipients.extend(cc)
            if bcc:
                if not isinstance(bcc, list):
                    bcc = bcc.split(',')
                msg['Bcc'] = ', '.join(bcc)
                recipients.extend(bcc)
            msg['Subject'] = subject
            if add_signature:
                signature = f'\n\n----------\nMessage created on {now} by Doberman slow control.'
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
            self.logger.info(f'Mail (Subject:{subject}) sent to {",".join(recipients)}')
        except Exception as e:
            self.logger.warning(f'Could not send mail: {e} ({type(e)})')
            return 0

    def send_sms(self, phone_numbers, message):
        """
        Send an SMS.
        Designed for usewith smscreator.de
        """
        # Get connection details
        connection_details = self.get_connection_details('websms')
        if connection_details is None:
            raise KeyError("No connection details obtained from database.")
        # Compose connection details and addresses
        url = connection_details['url']
        postparameters = connection_details['postparameters']
        maxmessagelength = int(connection_details['maxmessagelength'])
        if not phone_numbers:
            raise ValueError("No phone number given.")

        now = dtnow().replace(tzinfo=timezone.utc).astimezone(tz=None).strftime('%Y-%m-%dT%H:%M:%S')
        message = str(message)
        # Long messages are shortened to avoid excessive fees
        if len(message) > maxmessagelength:
            message = ' '.join(message[:maxmessagelength + 1].split(' ')[0:-1])
            self.logger.warning(f"Message exceeds {maxmessagelength} "
                                "characters. Message will be shortened.")

        if isinstance(phone_numbers, str):
            phone_numbers = [phone_numbers]
        for tonumber in phone_numbers:
            data = postparameters
            data['Recipient'] = tonumber
            data['SMSText'] = message
            data['SendDate'] = now
            self.logger.warning(f'Sending SMS to {tonumber}')
            response = requests.post(url, data=data)
            if response.status_code != 200:
                self.logger.error(f"Couldn't send message, status {response.status_code}: "
                                  f"{response.content.decode('ascii')}")

    def log_alarm(self, level=None, message=None, pipeline=None, _hash=None):
        """
        Sends 'message' to the contacts specified by 'level'.
        Returns 1 if all messages were sent successfully, 0 otherwise
        """
        ret = 1
        for protocol, recipients in self.db.get_contact_addresses(level).items():
            if protocol == 'sms':
                message = f'{self.db.experiment_name.upper()} {message}'
                if self.send_sms(recipients, message) == -1:
                    self.logger.error('Could not send SMS')
                    ret = 0
            elif protocol == 'email':
                subject = f'{self.db.experiment_name.capitalize()} level {level} alarm'
                if self.send_email(toaddr=recipients, subject=subject,
                                   message=message) == -1:
                    self.logger.error('Could not send email!')
                    ret = 0
            elif protocol == 'phone':
                try:
                    self.send_phonecall(recipients, message)
                except Exception as e:
                    self.logger.error(f'Unable to make call: {type(e)}, {e}')
                    ret = 0
            else:
                self.logger.warning(f"Couldn't send alarm message. Protocol {protocol} unknown.")
                ret = 0
        return ret

    def check_shifters(self):
        """
        Logs a notification (alarm) when the list of shifters changes
        """

        new_shifters = self.db.distinct('contacts', 'name', {'on_shift': True})
        new_shifters.sort()
        if new_shifters != self.current_shifters:
            if len(new_shifters) == 0:
                self.db.update_db('contact', {'name': {'$in': self.current_shifters}}, {'$set': {'on_shift': True}})
                self.log_alarm(level=1, message='No more allocated shifters.',
                               pipeline='AlarmMonitor',
                               _hash=Doberman.utils.make_hash(time.time(), 'AlarmMonitor'),
                               )
                self.db.update_db('contact', {'name': {'$in': self.current_shifters}}, {'$set': {'on_shift': False}})
                return
            msg = f'{", ".join(new_shifters)} '
            msg += ('is ' if len(new_shifters) == 1 else 'are ')
            msg += f'now on shift.'
            self.current_shifters = new_shifters
            self.log_alarm(level=1,
                           message=msg,
                           pipeline='AlarmMonitor',
                           _hash=Doberman.utils.make_hash(time.time(), 'AlarmMonitor'),
                           )
