# Introduction

For:
Litter-Robot 3 Connect
https://www.litter-robot.com/

The code attached MITMs the communication between the Litter Robot Connect and the server. This is accomplished
using an iptables rule on your router - basically:

     iptables -t nat -I PREROUTING -i eth1 -p tcp --dport 2000 -j DNAT --to 10.10.11.21

(not guaranteed to work as-written)

My goal was to translate this communication into MQTT or some other mechanism so that I can have real-time
alerts in a home automation scenario. Doing it this way also removes the need to continuously poll a remote API
or remember a username/password to re-authenticate.

The biggest challenge so far is that the Litter Robot rejects incoming messages without a valid checksum
value, and it rejects a message if the sequence number doesn't increment (which changes the checksum).

Related projects:

* UDP based (also hasn't figured out the checksum): https://github.com/mannkind/litterrobot/
* HTTP API based (Spelunk): https://github.com/sover02/ta-litter-robot
* HTTP API based (SmartThings App/DTH): https://github.com/natekspencer/LitterRobotManager/
* HTTP API based (Home Assistant): https://github.com/joshjcarrier/homeassistant-litter-robot
    
----

# Analysis

Copied from my original post on SmartThings forum:
https://community.smartthings.com/t/litter-robot-connect/106882/12?u=ydant

Once the litter robot is set up (using the iOS app), it communicates via UDP from port 2001 to a server running at dispatch.iothings.site on port 2000.

## Outgoing (Litter Robot to Server)

The protocol is pretty simple and consists of the Litter Robot device sending periodic stats updates to the server like so:

     >LR3,ff999aaafff000,H,AC,DFS,W7,NL1,SM0,PL0,CS0100,38FA,8A23DAFE

This breaks down to:

|Token            | Meaning
|-----------------|----------------------------------------------|
|`>`              | “outgoing message from Litter Robot to server”
|`LR3`            | Model number (Litter Robot 3?)
|`ff999aaafff000` | Unique ID for the registered device on the dispatch.iothings.site server
|`H`              | Not sure. I’ve only ever seen “H”.
|`AC`             | Power mode (AC / ??? for battery). Never seen anything other than AC in my installation.
|`Rdy`            | State (see below for known state codes)
|`W7`             | Wait time before cycling, in minutes (e.g. W7, W3, W10?)
|`NL1`            | Nightlight state (1 = on, 0 = off)
|`SM0`            | Sleep mode off - when on, the code is more complicated, like SM123:34:01. I haven’t tried to figure this out entirely, since I don’t use this.
|`PL0`            | Panel lock state (1 = locks, 0 = unlocked)
|`CS0100`         | not sure - this always starts with CS and has ranged from CS00CB to CS33FF in my current logged messages
|`38FA`           | Message number - increments every message. Resets to 0 when the unit is power cycled.
|`8A23DAFE`       | I think this is a checksum. I haven’t tried hard to get a consistent message (including message number) to see if this is entirely dependent on the message being sent.

Possible status codes and my best interpretation from memory:

| Status | Description |
|--------|-------------
| CCC    | Cat cycle completed
| CCP    | Cat cycle processing (spinning)
| CSF    | Cat sensor full (poop dump time)
| SDF    | Started Drawer Full? Only seen when powering up with a full drawer.
| CSI    | Cat sensor interrupted (cat got too curious mid-cycle)
| CST    | Cat sensor triggered (special present deposited, ready for processing)
| DF1    | Drawer is Full - Can cycle 2 more times
| DF2    | Drawer is Full - Can cycle 1 more time
| DFS    | Drawer is full - Will not cycle anymore
| BR     | Bonnet removed
| P      | Unit is Paused
| OFF    | Unit is turned off
| Rdy    | Ready for cats

(thanks, @Collisionc for the extra status codes interpretation)

On success, the server responds with a simple:

     AOK,ff999aaafff000

I don’t care much about fooling the server (or even care about the server until they have Android support), but I haven’t been able to spoof a message, since I don’t know how the checksum is generated.

## Incoming (Server to Litter Robot)

The server has a variety of control signals it can send. For example:

     <C,LR3,ff999aaafff000,06EB,7AE2E42F

     < - “incoming message from server to Litter Robot”
     LR3 - Model number (Litter Robot 3?)
     ff999aaafff000 - Target device ID
     06EB - Message counter (does not correspond to last outgoing message from Litter Robot)
     7AAAEEEF - I think this is a checksum. No idea how to generate this, and if it’s not right, the Litter Robot rejects the message.

From @Collisionc’s post on SmartThings:

Here are the incoming (server to litter robot) commands:

| Command       | Description 
|---------------|------------
| `<C`          | Start cleaning cycle
| `<W7`         | Set wait time to 7 minutes
| `<W3`         | Set wait time to 3 minutes
| `<WF`         | Set wait time to 15 minutes
| `<P0`         | Turn off
| `<P1`         | Turn on
| `<N1`         | Turn on night light
| `<N0`         | Turn off night light
| `<S0`         | Turn off sleep mode
| `<S119:45:02` | Turn on sleep mode, set to start at 19:45:02 MST – Kind of a guess here, it says 10 PM on the app when I use this, and I’m EST. I think it starts 15 minutes to prevent a cycle from happening after a 15 minute wait.
| `<L1`         | Turn on panel lock
| `<L0`         | Turn off panel lock

# Practical application

I’ve set up my router to redirect (outgoing NAT) all connections from the litter box to the server and send to a script I’m running on an internal computer. This allows me to intercept and relay all communications out to the Litter Robot server, and to route returned messages back to the Litter Robot. I have an EdgeRouter and I did this through the UI, but it could also be done with iptables similar to (the following may not work exactly, it was from my initial testing phase:

     iptables -t nat -I PREROUTING -i eth1 -p tcp --dport 2000 -j DNAT --to 10.10.11.21

Doing this allows me to do whatever I want with the status of the litter box (which is, honestly, all I really care about). From here, it’s only necessary to write the necessary code for SmartThings and bridge the interceptor with the SmartThings device code. I’m not horribly familiar with SmartThings, but I’ll work with someone if they want to do that part.

# Notes / Why

All of the IDs and checksums above are mocked. I don’t really want to publish my device’s ID, but I’m happy to work directly with someone who is more familiar with tracking down how to reverse engineer a checksum algorithm.

The only thing this would give you is the ability to control the litter box - which is of limited use to me. You can cycle the litter box, change settings, etc, but I can’t think of a real use for that as a remote function.

The main reason for this is my Litter Robot is hidden in my basement and I don't see it daily. It runs so consistently for 3-5 days without any intervention that if something does go wrong I don't notice until my cat gets very vocal with me and I finish checking the various normal irritants (not enough wet food, ears unscratched, water low, not enough petting) - then remember he also likes a clean bathroom. 

The Android Litter Robot app didn't exist when I started this project (Dec, 2017) and since it's come out I've figured out it's not good enough. Notifications on Android are easily swiped away and ignored, and the app doesn't persist if the robot's not working. What I have found to be very effective is to flash a warning light on a few key Inovelli Switches ( https://inovelli.com/shop/smart-light-switches/zwave-smart-switches-gen2/z-wave-on-off-switch-neutral-required-scenes-notifications/ ) around my house. I got this working with SmartThings and the web based API, but that API is slow, requires polling, and generally not as good as an instant notification through mqtt. So I'm dusting this project off, posting out, and maybe conquering the checksum this time.

Also, another note - the Litter Robot does not have a drawer full sensor, it just counts number of cycles. For your litter robot this may be accurate, but for mine this means what should be a once-a-week interaction actually has to happen on day 4/5. Extending this counter would be really good, so it's on my priority list. See the SmartThings discussion thread for some... discussion... about this.
