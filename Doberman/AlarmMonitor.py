import datetime
import time
from dateutil.tz import tzlocal
import re
import requests
import json
import smtplib
import Doberman
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

dtnow = datetime.datetime.utcnow

__all__ = 'AlarmMonitor'.split()


class AlarmMonitor(Doberman.Monitor):
    """
    Class that sends monitors for alarms and sends messages
    """

    def setup(self):
        now = dtnow()
        self.current_shifters = self.db.read_from_db('settings', 'shifts',
                {'start': {'$lte': now}, 'end': {'$gte': now}}, onlyone=True)['shifters']
        self.current_shifters.sort()
        self.register(obj=self.check_heartbeats, period=30, name='heartbeat')
        self.register(obj=self.check_for_alarms, period=5, name='alarmcheck')
        self.register(obj=self.check_shifters, period=60, name='shiftercheck')

    def get_connection_details(self, which):
        detail_doc = self.db.read_from_db('settings', 'alarm_config',
                                          {'connection_details': {'$exists': 1}}, onlyone=True)
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
            now = datetime.datetime.now().astimezone(tzlocal()).strftime("%Y-%m-%d %H:%M %Z")
            server_addr = connection_details['server']
            port = int(connection_details['port'])
            fromaddr = connection_details['fromaddr']
            password = connection_details['password']
            if not isinstance(toaddr, list):
                toaddr = toaddr.split(',')
            recipients = toaddr
            try:
                contactaddr = connection_details['contactaddr']
            except KeyError:
                contactaddr = '--'
            # Compose message
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
                signature = ("\n\n----------\n"
                             "Message created on %s by slow control. "
                             "This is a automatic message. "
                             % now)
                body = str(message) + signature
            else:
                body = str(message)
            msg.attach(MIMEText(body, 'plain'))
            # if available attach grafana plot of the last hour
            try:
                grafana_info = self.get_connection_details('grafana')
                to = int(1000 * time.time())
                fro = to - 3600000
                timezone = datetime.datetime.now(tzlocal()).tzname()
                reading_name = re.search('measurement (.*?):', str(message)).group(1)
                for name in grafana_info['panel_map'].keys():
                    if name in reading_name:
                        panel_id = int(grafana_info['panel_map'][name])
                        break
                url = f'{grafana_info["url"]}&from={fro}&to={to}&tz={timezone}&panelId={panel_id}'
                response = requests.get(url)
                msg.attach(MIMEImage(response.content))
            except Exception as e:
                self.logger.info(f'Didn\'t attach grafana plot, error: {str(e)} ({type(e)})')

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
                self.logger.warning("No phone number given. Can not send SMS.")
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
                self.logger.warning("SMS message exceets limit of 160 "
                                    "characters (%s characters). Message will "
                                    "be cut off." % str(len(message)))
                message = message[:155]
            cc = None
            if self.send_email(toaddr=toaddr,
                               subject=subject,
                               message=message,
                               cc=cc, bcc=bcc,
                               add_signature=False) == -1:
                self.logger.error("Could not send SMS! "
                                  "Email to SMS not working.")
                return -1

        except Exception as e:
            self.logger.error("Could not send sms, error: %s (%s)." % (e, type(e)))
            return -1
        return 0

    def check_for_alarms(self):
        doc_filter = {'acknowledged': {'$exists': 0}}
        messages = {}
        updates = {'$set': {'acknowledged': dtnow()}}
        db_col = ('logging', 'alarm_history')
        if self.db.count(*db_col, doc_filter) == 0:
            return
        for doc in self.db.read_from_db(*db_col, doc_filter, sort=[('howbad', -1)]):
            howbad = int(doc['howbad'])
            if (howbad,) not in messages:
                messages[(howbad,)] = []
            self.db.update_db(*db_col, {'_id': doc['_id']}, updates)
            messages[(howbad,)].append(doc)
        if messages:
            self.logger.warning(f'Found alarms!')
            for (lvl,), msg_docs in messages.items():
                message = ""
                for msg_doc in msg_docs:
                    msgtime = msg_doc["_id"].generation_time
                    msgtime = msgtime.astimezone(tzlocal()).strftime("%Y-%m-%d %H:%M %Z")
                    message += f'{msgtime}: {msg_doc["msg"]} \n'
                self.send_message(lvl, message)

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
                self.logger.warning(
                    f'Sent a message too recently ({dt:.0f} minutes). Message timer at {message_time:.0f}')
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

    def check_heartbeats(self):
        hosts = self.db.read_from_db('settings', 'hosts',
                                     {'status': {'$ne': 'offline'}})
        now = dtnow()
        for host in hosts:
            if (now - host['heartbeat']).total_seconds() > 2 * host['heartbeat_timer']:
                alarm_doc = {'name': 'alarm_monitor', 'howbad': 1,
                             'msg': 'Host "%s" hasn\'t heartbeated recently' % host['hostname']}
                self.db.log_alarm(alarm_doc)


    def check_shifters(self):
        """
        Logs a notification (alarm) when the list of shifters changes
        """

        now = dtnow()
        shift = self.db.read_from_db('settings', 'shifts',
                {'start': {'$lte': now}, 'end': {'$gte': now}}, onlyone=True)
        if shift == None:
            self.current_shifters = []
            return
        new_shifters = shift['shifters']
        new_shifters.sort()
        shift_end = shift['end']
        if new_shifters != self.current_shifters and len(''.join(new_shifters)) != 0:
            doc = {'name': 'alarm_monitor', 'howbad': 1,
                    'msg': f'Shifter change: {", ".join(new_shifters)} are now on shift until {shift_end.ctime()}.'}
            self.db.log_alarm(doc)
            self.current_shifters = new_shifters
