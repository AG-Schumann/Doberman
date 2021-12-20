import requests
import json
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import Doberman

dtnow = datetime.utcnow

__all__ = 'AlarmMonitor'.split()


class AlarmMonitor(Doberman.Monitor):
    """
    Class that sends monitors for alarms and sends messages
    """

    def setup(self):
        now = dtnow()
        self.current_shifters = self.db.read_from_db('settings', 'shifts',
                                                     {'start': {'$lte': now}, 'end': {'$gte': now}},
                                                     onlyone=True)['shifters']
        self.current_shifters.sort()
        self.register(obj=self.check_for_alarms, period=5, name='alarmcheck')
        self.register(obj=self.check_shifters, period=60, name='shiftercheck')

    def get_connection_details(self, which):
        detail_doc = self.db.get_experiment_config('alarm_config')
        try:
            return detail_doc['connection_details'][which]
        except KeyError:
            self.logger.critical('Could not load connection details for %s' % which)
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
            message = ' '.join(message[:maxmessagelength+1].split(' ')[0:-1])
            message = '<p>' + message + '</p>'
            message += '<p>Message shortened.</p>'
            self.logger.warning(f"Message exceeds {maxmessagelength} "
                                "characters. Message will be shortened.")
        message = f"This is the {self.db.experiment_name} alarm system. " + message
        if len(phone_numbers) == 1:
            phone_numbers = [phone_numbers]
        for tonumber in phone_numbers:
            data = {
                'To': tonumber,
                'From': fromnumber,
                'Parameters': json.dumps({'message': message})
            }
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
            self.logger.info(f'Mail (Subject:{subject}) sent')
        except Exception as e:
            self.logger.warning(f'Could not send mail: {e} ({type(e)})')
            return 0

    def send_sms(self, phone_number, message):
        """
        Sends an SMS.
        This works with sms sites which provide sms sending via email.
        """
        # Get connection details
        connection_details = self.get_connection_details('sms')
        if connection_details is None:
            return -1
        # Compose connection details and addresses
        try:
            server = connection_details['server']
            identification = connection_details['identification']
            contactaddr = connection_details['contactaddr']
            # fromaddr = connection_details['fromaddr']
            if not phone_number:
                self.logger.warning('No phone number given. Can not send SMS.')
                return 0
            # Server has different type request for 1 or several numbers.
            if len(phone_number) == 1:
                toaddr = f'{identification}.{phone_number[0]}@{server}'
                bcc = None
            else:
                toaddr = contactaddr
                bcc = [f'{identification}.{number}@{server}' for number in phone_number]
            message = str(message)
            subject = ''
            # Long SMS (>160 characters) cost more and are shortened
            if len(message) > 155:
                self.logger.warning('SMS message exceeds limit of 160 characters '
                                    f'({len(message)} characters). '
                                    'Message will be cut off.')
                message = message[:155]
            cc = None
            if self.send_email(toaddr=toaddr,
                               subject=subject,
                               message=message,
                               cc=cc, bcc=bcc,
                               add_signature=False) == -1:
                self.logger.error('Could not send SMS! Email to SMS not working.')
                return -1

        except Exception as e:
            self.logger.error(f'Could not send SMS: {e}, {type(e)}')
            return -1
        return 0

    def check_for_alarms(self):
        doc_filter = {'acknowledged': 0}
        messages = {}
        updates = {'$set': {'acknowledged': dtnow()}}
        db_col = ('logging', 'alarm_history')
        if self.db.count(*db_col, doc_filter) == 0:
            return
        for doc in self.db._check(*db_col).aggregate([
            {'$match': doc_filter},
            {'$group': {
                '_id': '$howbad',
                'logged': {'$push': {'$toDate': '$_id'}},
                'msgs': {'$push': '$msg'}}}]):
            message = '\n'.join([f'{d.iso_format()}: {m}' for d,m in zip(doc['logged'], doc['msgs'])])
            self.send_message(doc['_id'], message)
        # put the update at the end so if something goes wrong with the message sending then the
        # alarms don't get acknowledged and lost
        self.db.update_db(*db_col, doc_filter, updates)
        return

    def send_message(self, level, message):
        """
        Sends 'message' to the contacts specified by 'level'
        """
        now = dtnow()
        message_time = self.db.get_runmode_setting(runmode='default',
                                                   field='message_time')
        if hasattr(self, 'last_message_time') and self.last_message_time is not None:
            dt = (now - self.last_message_time).total_seconds() / 60
            if dt < message_time:
                self.logger.warning(f'Sent a message too recently ({dt:.0f} minutes). '
                                    f'Message timer at {message_time:.0f}')
                return
        for protocol, recipients in self.db.get_contact_addresses(level).items():
            if protocol == 'sms':
                message = f'{self.db.experiment_name.upper()} {message}'
                if self.send_sms(recipients, message) == -1:
                    self.logger.error('Could not send SMS')
            elif protocol == 'email':
                subject = f'{self.db.experiment_name.capitalize()} level {level} alarm'
                if self.send_email(toaddr=recipients, subject=subject,
                                   message=message) == -1:
                    self.logger.error('Could not send email!')
            elif protocol == 'phone':
                try:
                    self.send_phonecall(recipients, message)
                except Exception as e:
                    self.logger.error('Unable to make call: {type(e)}, {e}')
            else:
                self.logger.warning(f"Couldn't send alarm message. Protocol {protocol} unknown.")
            self.last_message_time = now

    def check_shifters(self):
        """
        Logs a notification (alarm) when the list of shifters changes
        """

        now = dtnow()
        shift = self.db.read_from_db('settings', 'shifts',
                                     {'start': {'$lte': now}, 'end': {'$gte': now}}, onlyone=True)
        if shift is None:
            self.current_shifters = []
            return
        new_shifters = shift['shifters']
        new_shifters.sort()
        if new_shifters != self.current_shifters:
            if len(''.join(new_shifters)) == 0:
                self.logger.info('No more allocated shifters.')
                return

            end_time = shift['end'].replace(tzinfo=timezone.utc).astimezone(tz=None)
            shifters = list(filter(None, new_shifters))
            msg = f'{", ".join(shifters)} '
            msg += ('is ' if len(shifters) == 1 else 'are ')
            msg += f'now on shift until {end_time.strftime("%b %-d %H:%M")}.'
            doc = {'name': 'alarm_monitor', 'howbad': 1, 'msg': msg}
            self.db.log_alarm(doc)
            self.current_shifters = new_shifters

