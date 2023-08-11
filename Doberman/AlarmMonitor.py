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
            raise KeyError("No phone connection details obtained from database.")
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
            self.logger.warning(f"Message exceeds {maxmessagelength} characters. Message will be shortened.")
        message = f"This is the {self.db.experiment_name} alarm system. " + message
        if isinstance(phone_numbers, str):
            phone_numbers = [phone_numbers]
        self.logger.warning(f'Making phone call to {len(phone_numbers)} recipient{"s" if len(phone_numbers)>1 else ""}')
        for tonumber in phone_numbers:
            data = {
                'To': tonumber,
                'From': fromnumber,
                'Parameters': json.dumps({'message': message})
            }
            response = requests.post(url, auth=auth, data=data)
            if response.status_code != 201:
                raise RuntimeError(f"Couldn't place call, status"
                                   + f" {response.status_code}: {response.json()['message']}")

    def send_email(self, addresses, subject, message, level, pipeline):
        # Get connection details
        connection_details = self.get_connection_details('email')
        if connection_details is None:
            raise ValueError("No email connection details found")
        # Compose connection details and addresses
        now = dtnow().replace(tzinfo=timezone.utc).astimezone(tz=None).strftime("%Y-%m-%d %H:%M %Z")
        server_addr = connection_details['server']
        port = int(connection_details['port'])
        fromaddr = connection_details['fromaddr']
        password = connection_details['password']
        if not isinstance(addresses, list):
            addresses = addresses.split(',')
        msg = MIMEMultipart()
        msg['From'] = fromaddr
        msg['To'] = ', '.join(addresses)
        msg['Subject'] = subject
        message = f'<b>{message}</b>'
        if website_url := connection_details.get('website', None):
            # add links to view sensors of the pipeline
            message += f'<br><br>Show sensors involved in this pipeline:<ul>'
            sensors = self.db.get_pipeline(pipeline).get('depends_on', [])
            for sensor in sensors:
                message += f'<li><a href="{website_url}?sensor={sensor}">{sensor}</a></li>'
            message += '</ul>'
        silence_duration = self.db.get_experiment_config('alarm').get('silence_duration')[level]
        message += f'This alarm is automatically silenced for <b>{int(silence_duration / 60)} minutes</b>.'
        if website_url:
            # add manual silence options
            message += '<br><br>To silence the pipeline for longer, click one of the following links:<ul>'
            for silence_for, text in zip((15, 60, 360), ('15 minutes', '1 hour', '6 hours')):
                if silence_for > int(silence_duration / 60):
                    message += f'<li><a href="{website_url}/pipeline?pipeline={pipeline}&silence={silence_for}">' \
                               f'{text}</a></li> '
            message += '</ul>'
        message += f'<hr>Message created on {now} by Doberman slow control.'
        msg.attach(MIMEText(message, 'html'))
        # Connect and send
        self.logger.warning(f'Sending e-mail to {len(addresses)} recipient{"s" if len(addresses)>1 else ""}')
        if server_addr == 'localhost':  # From localhost
            smtp = smtplib.SMTP(server_addr)
            smtp.sendmail(fromaddr, addresses, msg.as_string())
        else:  # with e.g. gmail
            server = smtplib.SMTP(server_addr, port)
            server.starttls()
            server.login(fromaddr, password)
            server.sendmail(fromaddr, addresses, msg.as_string())
            server.quit()

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
            self.logger.warning(f"Message exceeds {maxmessagelength} characters. Message will be shortened.")
        if isinstance(phone_numbers, str):
            phone_numbers = [phone_numbers]
        self.logger.warning(f'Sending SMS to {len(phone_numbers)} recipient{"s" if len(phone_numbers)>1 else ""}')
        for tonumber in phone_numbers:
            data = postparameters
            data['Recipient'] = tonumber
            data['SMSText'] = message
            data['SendDate'] = now
            response = requests.post(url, data=data)
            if response.status_code != 200:
                raise RuntimeError(f"Couldn't send message, status {response.status_code}: "
                                   f"{response.content.decode('ascii')}")

    def log_alarm(self, level=None, message=None, pipeline=None, _hash=None, prot_rec_dict=None):
        """
        Sends 'message' to the contacts specified by 'level'.
        """
        exception = None
        if not prot_rec_dict:
            prot_rec_dict = self.db.get_contact_addresses(level)
        for protocol, recipients in prot_rec_dict.items():
            try:
                if protocol == 'sms':
                    message = f'{self.db.experiment_name.upper()} {message}'
                    self.send_sms(recipients, message)
                elif protocol == 'email':
                    subject = f'{self.db.experiment_name.capitalize()} level {level} alarm'
                    self.send_email(addresses=recipients, subject=subject, message=message, level=level, pipeline=pipeline)
                elif protocol == 'phone':
                    self.send_phonecall(recipients, message)
                else:
                    raise ValueError(f"Couldn't send alarm message. Protocol {protocol} unknown.")
            except Exception as e:
                exception = e  # Save it for later but try other methods anyway
        if exception is not None:
            raise exception

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
