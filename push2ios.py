"""
django-ios-push - Django Application for doing iOS Push Notifications
Originally written by Lee Packham (http://leenux.org.uk/ http://github.com/leepa)
Updated by Wojtek 'suda' Siudzinski <wojtek@appsome.co>

(c)2009 Lee Packham - ALL RIGHTS RESERVED
May not be used for commercial applications without prior concent.
"""

import socket
import struct
import ssl
import binascii
import time
import threading


# Set this to the hostname for the outgoing push server
APN_SANDBOX_HOST = 'gateway.sandbox.push.apple.com'
APN_LIVE_HOST = 'gateway.push.apple.com'

# Set this to the hostname for the feedback server
APN_SANDBOX_FEEDBACK_HOST = 'feedback.sandbox.push.apple.com'
APN_LIVE_FEEDBACK_HOST = 'feedback.push.apple.com'


# Handle Python 2.5 / 2.6 seamlessly
try:
    import json
except ImportError:
    import simplejson as json


class ErrorTokenException(Exception):
    pass


class ResponseThd(threading.Thread):
    def __init__(self, passed_socket, err_list):
        super(ResponseThd, self).__init__()
        self._stop = False
        self.c = passed_socket
        self.err_list = err_list

    def run(self):
        while not self._stop:
            response = self.c.read()
            if len(response) > 0:
                response_command, response_status, response_identifier = struct.unpack("!BBI", response)
                self.err_list.append(response_identifier)
                close_connection(self.c)
                return
            time.sleep(0.1)

    def stop(self):
        self._stop = True
        close_connection(self.c)


def close_connection(c):
    try:
        c.shutdown(socket.SHUT_RDWR)
        c.close()
    except Exception, ex:
        print "close connection", ex


def send_message(device_token, alert, badge=0, sound="chime", content_available=False,
                    custom_params={}, action_loc_key=None, loc_key=None,
                    loc_args=[], passed_socket=None, custom_cert=None,
                    identifier=0, expiry=0, debug=True):
    aps_payload = {}
    alert_payload = alert
    if action_loc_key or loc_key or loc_args:
        alert_payload = {'body' : alert}
        if action_loc_key:
            alert_payload['action-loc-key'] = action_loc_key
        if loc_key:
            alert_payload['loc-key'] = loc_key
        if loc_args:
            alert_payload['loc-args'] = loc_args

    aps_payload['alert'] = alert_payload
    if badge:
        aps_payload['badge'] = badge
    if sound:
        aps_payload['sound'] = sound
    if content_available:
        aps_payload['content-available'] = 1
    payload = custom_params
    payload['aps'] = aps_payload

    # This ensures that we strip any whitespace to fit in the 256 bytes
    s_payload = json.dumps(payload, separators=(',',':'), ensure_ascii=False).encode('utf8')

    fmt = "!cIIH32sH%ds" % len(s_payload)
    command = '\x01'
    try:
        device_token_content = device_token.replace(' ', '').strip()
        msg = struct.pack(fmt, command, identifier, expiry, 32, binascii.unhexlify(device_token_content), len(s_payload), s_payload)
    except Exception, ex:
        print ex
        raise ErrorTokenException("Error token: %s" % device_token_content)

    if passed_socket:
        c = passed_socket
    else:
        s = socket.socket()
        c = ssl.wrap_socket(s, ssl_version=ssl.PROTOCOL_SSLv3, certfile=custom_cert)
        c.connect((APN_LIVE_HOST, 2195))

    c.write(msg)

    if not passed_socket:
        c.close()


def rebuild_connection(custom_cert, host_name):
    s = socket.socket()
    c = ssl.wrap_socket(s, ssl_version=ssl.PROTOCOL_TLSv1, certfile=custom_cert)
    c.connect((host_name, 2195))

    return c


def sendMessageToPhoneGroup(devices_token_list, alert, badge=0, sound="chime", content_available=False,
                            custom_params={}, action_loc_key=None, loc_key=None,
                            loc_args=[], sandbox=False, custom_cert=None, expiry=0):
    if sandbox:
        host_name = APN_SANDBOX_HOST
    else:
        host_name = APN_LIVE_HOST

    chunk_size = 100
    current_chunk = 0

    thd_pool = []

    list_length = len(devices_token_list)
    err_list = list()

    c = rebuild_connection(custom_cert, host_name)

    thd = ResponseThd(c, err_list)
    thd.start()
    thd_pool.append(thd)

    current_index = 0
    err_count = 0
    try:
        while current_index <= list_length - 1:
            if err_list:
                err_id = err_list.pop(0)
                c = rebuild_connection(custom_cert, host_name)
                current_index = err_id + 1
                err_list = list()
                err_count += 1

                thd = ResponseThd(c, err_list)
                thd.start()
                thd_pool.append(thd)

                current_chunk = 0

            device_token = devices_token_list[current_index]
            try:
                send_message(device_token, alert, badge=badge, sound=sound, content_available=content_available, custom_cert=custom_cert, passed_socket=c, custom_params=custom_params, action_loc_key=action_loc_key, loc_key=loc_key, loc_args=loc_args, identifier=current_index, expiry=expiry)
            except ErrorTokenException, ex:
                print ex

            if current_index == list_length - 1:
                time.sleep(2)
                if err_list:
                    err_id = err_list.pop(0)
                    c = rebuild_connection(custom_cert, host_name)
                    current_index = err_id + 1
                    err_list = list()
                    err_count += 1

                    thd = ResponseThd(c, err_list)
                    thd.start()
                    thd_pool.append(thd)

                    current_chunk = 0

                    continue
            current_index += 1

            if current_chunk > chunk_size:
                err_list = []
                c = rebuild_connection(custom_cert, host_name)
                current_chunk = 0
                thd = ResponseThd(c, err_list)
                thd.start()
                thd_pool.append(thd)

            current_chunk += 1
    except Exception, ex:
        print ex

    finally:
        for thd in thd_pool:
            thd.stop()

def doFeedbackLoop(cert, sandbox=False):
    pass
