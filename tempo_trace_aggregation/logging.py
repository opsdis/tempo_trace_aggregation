# -*- coding: utf-8 -*-
"""
    Copyright (C) 2022  Anders Håål and Redbridge AB

    This file is part of tta - Tempo trace aggregation.

    indis is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    indis is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with tta.  If not, see <http://www.gnu.org/licenses/>.

"""

import datetime
import json
import logging
import numbers
import os
import sys
from typing import Any

from dateutil.tz import tzutc

MESSAGE = 'message'


class Iso8601UTCTimeFormatter(logging.Formatter):

    def __init__(self, log_format=None, time_format=None):
        """
        The purpose of this constructor is to set the timezone to UTC for later use.

        :param log_format: Log record formatting string.
        :type log_format: str
        :param time_format: Time formatting string. You probably **DO NOT** want one.
        :type time_format: str
        """
        super(Iso8601UTCTimeFormatter, self).__init__(log_format, time_format)

        self._TIMEZONE_UTC = tzutc()

    def formatTime(self, record, timeFormat=None):
        if timeFormat is not None:
            return super(Iso8601UTCTimeFormatter, self).formatTime(record, timeFormat)

        return str(datetime.datetime.fromtimestamp(record.created, self._TIMEZONE_UTC).isoformat(
            timespec='milliseconds')).replace('+00:00', 'Z')


class Log:

    def __init__(self, name):
        self.logger = self.configure_logger(name)

    def error(self, message):
        self.error_fmt({MESSAGE: message})

    def warn(self, message):
        self.warn_fmt({MESSAGE: message})

    def info(self, message):
        self.info_fmt({MESSAGE: message})

    def debug(self, message):
        self.debug_fmt({MESSAGE: message})

    def operation(self, oper: str, mesg: str, level: str = 'INFO', id: Any = None):
        log_kv = {'operation': oper, MESSAGE: mesg, 'id': id}
        if level == 'INFO':
            self.info_fmt(log_kv)
        if level == 'WARN':
            self.warn_fmt(log_kv)
        if level == 'ERROR':
            self.error_fmt(log_kv)

    def info_fmt(self, log_kv: dict, message: str = None):
        fmt = self._create_fmt(log_kv, message)
        self.logger.info(fmt)

    def warn_fmt(self, log_kv: dict, message: str = None):
        fmt = self._create_fmt(log_kv, message)
        self.logger.warning(fmt)

    def error_fmt(self, log_kv: dict, message: str = None):
        fmt = self._create_fmt(log_kv, message)
        self.logger.error(fmt)

    def debug_fmt(self, log_kv: dict, message: str = None):
        fmt = self._create_fmt(log_kv, message)
        self.logger.debug(fmt)

    def dump_command(self, command, status, response_text, url, body=None):
        self.info_fmt(
            {'operation': 'dump', 'command': command, 'status': status, 'response_text': response_text, 'url': url,
             'body': json.dumps(body)})

    def info_timer(self, method, path, object_name, time, num_of_calls=None, status=None, remote_address: str = None):
        self.info_fmt(
            {'system': 'icinga2', 'address': remote_address, 'method': method, 'path': path, 'object': object_name,
             'status': status, 'response_time': time})

    def _create_fmt(self, log_kv, message):
        if message:
            _log_kv = dict(log_kv)
            _log_kv[MESSAGE] = message
            fmt = self._format(_log_kv)
        else:
            fmt = self._format(log_kv)
        return fmt

    def _format(self, log_kv):
        fmt = ''
        sep = ''
        try:
            for k, v in log_kv.items():
                if v is not None:
                    if isinstance(v, numbers.Number):
                        fmt = f"{fmt}{sep}{k}={str(v)}"
                    elif ' ' in v or '"' in v:
                        if '"' in v:
                            j = v.replace('"', '\\"')
                            fmt = f"{fmt}{sep}{k}=\"{j}\""
                        else:
                            fmt = f"{fmt}{sep}{k}=\"{v}\""
                    else:
                        fmt = f"{fmt}{sep}{k}={v}"
                sep = ' '
            return fmt
        except Exception as err:
            return f"exception=\"{err}\" description=\"Parsing log entry\""

    def infotimer(self, system, method, path, time, num_of_calls=None, status=None):
        self.info_fmt({'system': system, 'method': method, 'path': path, 'status': status, 'response_time': time,
                       'calls': num_of_calls})

    def configure_logger(self, name):
        formatter = Iso8601UTCTimeFormatter('timestamp=%(asctime)s level=%(levelname)s %(message)s')

        logger = logging.getLogger(name)
        logger.setLevel('INFO')
        try:
            hdlr = logging.StreamHandler(sys.stdout)

            if os.getenv('INDIS_LOG_FILE'):
                hdlr = logging.FileHandler(os.getenv('INDIS_LOG_FILE'))

            hdlr.setFormatter(formatter)
            logger.addHandler(hdlr)

            if os.getenv('INDIS_LOG_LEVEL'):
                logger.setLevel(os.getenv('INDIS_LOG_LEVEL'))

        except Exception:

            hdlr = logging.StreamHandler(sys.stdout)
            if os.getenv('INDIS_LOG_FILE'):
                hdlr = logging.FileHandler(os.getenv('INDIS_LOG_FILE'))

            hdlr.setFormatter(formatter)
            logger.addHandler(hdlr)
            logger.setLevel('INFO')
            if os.getenv('INDIS_LOG_LEVEL'):
                logger.setLevel(os.getenv('INDIS_LOG_LEVEL'))

        return logger
