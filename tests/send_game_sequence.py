"""Manual acceptance aid: run only with truck parked in the cabin.

Sends directly to SCS bridge, no webcam and no OpenTrack required.
"""
import socket
import struct
import time

with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sender:
    try:
        for label,yaw,pitch in [('centro',0,0),('yaw +30',30,0),('centro',0,0),
                                ('yaw -30',-30,0),('pitch +15',0,15),('pitch -15',0,-15),('centro',0,0)]:
            print(label,flush=True)
            end=time.monotonic()+3
            while time.monotonic()<end:
                sender.sendto(struct.pack('<6d',0,0,0,yaw,pitch,0),('127.0.0.1',4243))
                time.sleep(1/60)
    finally:sender.sendto(struct.pack('<6d',0,0,0,0,0,0),('127.0.0.1',4243))
