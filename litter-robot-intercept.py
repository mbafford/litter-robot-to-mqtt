#!/usr/bin/env python3

import sqlite3

import datetime
import socket
import select
import time
import sys

import json

import paho.mqtt.client as mqtt

DEBUG=False

# Remote server is at dispatch.iothings.site UDP 2001
# Local device is at 10.10.70.9 and sends traffic from 2000 to 2001

# DNAT rule on the router translates this into connecting to 10.10.11.21 port 2000

# Messages should be relayed to dispatch.iothings.site port 2000
# which will respond back to port 2000 on our external IP
# which will get forwarded to 2000 on 10.10.11.21
# which will then forward to the litter-robot


PORT_SERVER = 2001                     # the port we use for pretending to be the remote server
PORT_LITTER = 2000                     # the port we use for pretending to be the litter box
IP_LITTER   = "10.10.70.9"             # the IP address to use to send messages to the litter box
HOST_SERVER = "dispatch.iothings.site" # the remote server hostname

MQTT_HOST="10.10.10.198"
MQTT_PORT=1883
MQTT_USER=None
MQTT_PASS=None

columns    = ["ts", "src", "cmd", "model", "device_id", "unk4", "power", "status", "wait", "light", "sleep_mode", "sleep_time", "lock", "cs_code", "y_code", "ack_num", "msg_num", "chksum"]
sql_insert = "insert into messages(%s) values( %s )"  % ( ",".join(columns), ",".join([ "?" for c in columns ]) )

statuses = {
    "CCC": { "error": False, "desc": "Cycle complete"                                       },
    "CCP": { "error": False, "desc": "Cycle in process"                                     },
    "CSF": { "error": True,  "desc": "Cat sensor fault"                                     },
    "SCF": { "error": True,  "desc": "Started with cat sensor fault"                        },
    "CSI": { "error": False, "desc": "Cat sensor interrupted"                               },
    "CST": { "error": False, "desc": "Cat sensor triggered"                                 },
    "DF1": { "error": False, "desc": "Drawer full - warning 1"                              },
    "DF2": { "error": False, "desc": "Drawer full - warning 2"                              },
    "DFS": { "error": True,  "desc": "Drawer full - stopped"                                },
    "SDF": { "error": True,  "desc": "Started with drawer full"                             },
    "BR" : { "error": True,  "desc": "Bonnet removed - unit stopped"                        },
    "P"  : { "error": True,  "desc": "Unit paused"                                          },
    "OFF": { "error": True,  "desc": "Unit is disabled (soft off)"                          },
    "Rdy": { "error": False, "desc": "Unit is ready and ok"                                 },
    "MIA": { "error": True,  "desc": "Missing in action. Possible error with local server." },
}

commands = {
    "C" : "Start cleaning cycle",
    "W7": "Set wait time 7 minutes",
    "W3": "Set wait time 3 minutes",
    "WF": "Set wait time 15 minutes",
    "P0": "Set power off (soft off)",
    "P1": "Set power on",
    "N1": "Turn nightlight on",
    "N0": "Turn nightlight off",
    "S0": "Turn off sleep mode",
    "S1": "Turn on sleep mode",
    "L0": "Turn off panel lock",
    "L1": "Turn on panel lock",
}

LOG_DB   = None
LOG_FILE = None
if len(sys.argv) > 1:
    LOG_DB=sys.argv[1]
if len(sys.argv) > 2:
    LOG_FILE=sys.argv[2]

if LOG_DB:
    db_conn = sqlite3.connect(LOG_DB)
    c = db_conn.cursor()
    c.execute("create table if not exists messages(%s)" % ",".join(columns))
    db_conn.commit()

def log( msg ):
    if LOG_FILE:
        with open(LOG_FILE, 'a') as f:
            f.write(msg)
            f.write("\n")
            f.flush()
    print( msg )

def save( msg ):
    if not db_conn: return
    c = db_conn.cursor()
    values = [ msg.get( c, None ) for c in columns ]

    c.execute( sql_insert, values )
    db_conn.commit()


def on_mqtt_connect(client, userdata, flags, rc):
    print("Connected to MQTT server with result code: %s" % str(rc))
    client.will_set("litter_robot", json.dumps({"status": "MIA", "error": True, "desc": statuses['MIA']}))

client = mqtt.Client()
client.on_connect = on_mqtt_connect
client.connect_async(MQTT_HOST, MQTT_PORT, 60)
client.loop_start()

sock_litter = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock_litter.bind(('0.0.0.0', PORT_LITTER))

sock_server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock_server.bind(('0.0.0.0', PORT_SERVER))

def handle_from_robot( raw_data, addr ):
    try:
        msg = raw_data.strip().decode()
    except:
        log("handle_from_robot: error parsing %s from %s" % (raw_data, addr))
        return

    
    parsed_msg   = None
    save_to_db   = False
    post_to_mqtt = False

    parts = msg.split(",") 
    if len(parts) == 12:
        parsed_msg = {
            'ts':          int(time.time()),
            'src':         "robot",          # source of the message - robot or server
            'dir':         parts[ 0][0],     # > (robot to server) or < (server to robot)
            'model':       parts[ 0][1:],    # strip off the ">" or "<" for direction
            'device_id':   parts[ 1],        # e.g. 5c3f312af824b9
            'unk4':        parts[ 2],        # H       - only ever seen "H"
            'power':       parts[ 3],        # AC      - will change for battery
            'status':      parts[ 4],        # Rdy,    - long list of potential values 
            'wait':        parts[ 5],        # W7      - wait time before cycling (W3, W7, etc)
            'light':       parts[ 6],        # NL1     - nightlight status (1=on, 0=off)
            'sleep_mode':  parts[ 7][0:3],   # SM0     - sleep mode - SM0 = off, SM1 = on
            'sleep_time':  parts[ 7][3:],    # SM0     - sleep mode - SM0 = off, also seen SM123:34:01 
            'lock':        parts[ 8],        # PL0     - panel lock (1=on, 0=off)
            'cs_code':     parts[ 9],        # CS00E3  - 
            'msg_num':     parts[10],        # 0710 0711
            'chksum':      parts[11],        # 00D28BBA
            'error':       statuses.get( parts[4], {} ).get('error', True), # treat unknown statuses as errors
            'desc':        statuses.get( parts[4], {} ).get('desc',  'Unknown status code'),
        }

        save_to_db   = True
        post_to_mqtt = True

    elif len(parts) == 6:
        parsed_msg = {
            'ts':          int(time.time()),
            'src':         'robot',
            'dir':         parts[0][0],
            'model':       parts[0][1:],
            'device_id':   parts[1],
            'unk4':        parts[2],
            'y_code':      parts[3],
            'msg_num':     parts[4],
            'chksum':      parts[5],
        }

        save_to_db   = True
        post_to_mqtt = False

    elif len(parts) == 5 and ( parts[0] == "NOK" or parts[0] == "AOK" ):
        parsed_msg = {
            'ts':          int(time.time()),
            'src':         'robot',
            'cmd':         parts[0],
            'device_id':   parts[1],
            'ack_num':     parts[2],
            'msg_num':     parts[3],
            'chksum':      parts[4],
        }

        save_to_db   = True
        post_to_mqtt = False
        
    if parsed_msg:
        log("%-27s %-16s %5d FROM_LITTER     %s" % ( datetime.datetime.now().isoformat(), addr[0], addr[1], msg ) )
        if save_to_db:   save( parsed_msg )
        if post_to_mqtt: client.publish("litter_robot/" + parsed_msg['device_id'] + '/status', json.dumps(parsed_msg), retain=True)
    else:
        log("%-27s %-16s %5d FROM_LITTER UNK %s" % ( datetime.datetime.now().isoformat(), addr[0], addr[1], msg ) )

    # pass on the exact data sent from the litter box to the server, unchanged
    sent = sock_litter.sendto(raw_data, ("dispatch.iothings.site", 2001))
    
    if DEBUG: log("%-27s %-16s %5d TO_SERVER   OK  %s" % ( datetime.datetime.now().isoformat(), addr[0], addr[1], msg ) )
    
    return

def handle_from_server( raw_data, addr ):
    try:
        msg = raw_data.strip().decode()
    except:
        log("handle_from_server: error parsing %s from %s" % (raw_data, addr))
        return

    parsed_msg   = None
    save_to_db   = False
    post_to_mqtt = False

    parts = msg.split(",") 
    if len(parts) == 5:
        parsed_msg = {
            'ts':          int(time.time()),
            'src':         "server",        # source of the message - robot or server
            'dir':         parts[0][0],     # > (robot to server) or < (server to robot)
            'cmd':         parts[0][1:],    # strip off the ">" or "<" for direction
            'model':       parts[1],
            'device_id':   parts[2],        # e.g. 5c3f312af824b9
            'msg_num':     parts[3],        # 0710 0711
            'chksum':      parts[4],        # 00D28BBA 
        }
        save_to_db   = True
        post_to_mqtt = False

    elif len(parts) == 2 and ( parts[0] == "NOK" or parts[0] == "AOK" ):
        parsed_msg = {
            'ts':          int(time.time()),
            'src':         'server',
            'cmd':         parts[0],
            'device_id':   parts[1],
        }
        
        save_to_db   = False
        post_to_mqtt = False


    if parsed_msg:
        if save_to_db:   save( parsed_msg )
        if post_to_mqtt: client.publish("litter_robot/" + parsed_msg['device_id'] + '/server', json.dumps(parsed_msg), retain=False)

        log("%-27s %-16s %5d FROM_SERVER     %s" % ( datetime.datetime.now().isoformat(), addr[0], addr[1], msg ) )
    else:
        log("%-27s %-16s %5d FROM_SERVER UNK %s" % ( datetime.datetime.now().isoformat(), addr[0], addr[1], msg ) )

    # pass on the exact data sent from the server on to the litter box, unchanged
    sent = sock_server.sendto(raw_data, (IP_LITTER, 2000))
    
    if DEBUG: log("%-27s %-16s %5d TO_LITTER   OK  %s" % ( datetime.datetime.now().isoformat(), addr[0], addr[1], msg ) )

    return

while True:
    read, write, error = select.select([sock_server, sock_litter], [], [])

    for r in read:
        data, addr = r.recvfrom(1024)

        if   r == sock_server: handle_from_robot ( data, addr )
        elif r == sock_litter: handle_from_server( data, addr )
