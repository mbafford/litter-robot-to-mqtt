#!/usr/bin/env python3

import datetime
import socket
import select
import sys

# the port we use for pretending to be the remote server
PORT_SERVER=2001

# the port we use for pretending to be the litter box
PORT_LITTER=2000

# the IP address to use to send messages to the litter box
IP_LITTER="10.10.70.9"

# the remote server hostname
HOST_SERVER="dispatch.iothings.site"

OUT_FILE=None
if len(sys.argv) > 1:
    OUT_FILE=sys.argv[1]

def log( msg ):
    if OUT_FILE:
        with open(OUT_FILE, 'a') as f:
            f.write(msg)
            f.write("\n")
            f.flush()
    print( msg )

# Remote server is at
# dispatch.iothings.site
# 2001

# Local device is at
# 10.10.70.9 and sends traffic from 2000 to 2001

# DNAT rule on the router translates this into 
# connecting to 10.10.11.21 port 2000

# Messages should be relayed to dispatch.iothings.site port 2000
# which will respond back to port 2000 on our external IP
# which will get forwarded to 2000 on 10.10.11.21

# which will then forward to the litter-robot

sock_litter = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock_litter.bind(('0.0.0.0', PORT_LITTER))

sock_server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock_server.bind(('0.0.0.0', PORT_SERVER))

def handle_from_litter( raw_data, addr ):
    try:
        msg = raw_data.strip().decode()
    except:
        log("handle_from_litter: error parsing %s from %s" % (raw_data, addr))
        return

    log("%-27s %-16s %5d FROM_LITTER OK  %s" % ( datetime.datetime.now().isoformat(), addr[0], addr[1], msg ) )

    # parts = text.split(",") 

    #msg = {
    #    'model':  parts[ 0],
    #    'serial': parts[ 1],
    #    'unk1':   parts[ 2], # H
    #    'power':  parts[ 3], # AC
    #    'status': parts[ 4], # Rdy, 
    #    'wait':   parts[ 5], # W7 (wait 7 min)
    #    'light':  parts[ 6], # NL1 (nightlight on)
    #    'sleep':  parts[ 7], # SM0 (sleep mode off?) - SM123:34:01 
    #    'lock':   parts[ 8], # PL0 (panel lock off)
    #    'unk6':   parts[ 9], # CS00E3
    #    'msgnum': parts[10], # 0710 0711
    #    'chksum': parts[11], # 00D28BBA 
    #}
    
    # print( "%-13s %s" % ( addr[0], " ".join(parts) ) )

    # pass on the exact data sent from the litter box to the server, unchanged
    sent = sock_litter.sendto(raw_data, ("dispatch.iothings.site", 2001))
    
    log("%-27s %-16s %5d TO_SERVER   OK  %s" % ( datetime.datetime.now().isoformat(), addr[0], addr[1], msg ) )
    
    return

def handle_from_server( raw_data, addr ):
    try:
        msg = raw_data.strip().decode()
    except:
        log("handle_from_server: error parsing %s from %s" % (raw_data, addr))
        return


    log("%-27s %-16s %5d FROM_SERVER OK  %s" % ( datetime.datetime.now().isoformat(), addr[0], addr[1], msg ) )

    # pass on the exact data sent from the server on to the litter box, unchanged
    sent = sock_server.sendto(raw_data, (IP_LITTER, 2000))
    
    log("%-27s %-16s %5d TO_LITTER   OK  %s" % ( datetime.datetime.now().isoformat(), addr[0], addr[1], msg ) )

    return

while True:
    read, write, error = select.select([sock_server, sock_litter], [], [])

    for r in read:
        data, addr = r.recvfrom(1024)

        if   r == sock_server: handle_from_litter( data, addr )
        elif r == sock_litter: handle_from_server( data, addr )
