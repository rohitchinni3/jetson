import zmq
import threading
import time
from gps import *
import math
from enum import Enum

class Results(Enum):
    Failure = 0
    Success = 1

def decoded(s):
    return int.from_bytes(s, 'little')

def encoded(value, length):
    return value.to_bytes(length, 'little')

class Integer8():
    def __init__(self):
        self.value = None

    def encode(self):
        if self.value is None:
            return None
        return encoded(self.value, 1)

    def decode(self, s):
        self.value = decoded(s[:1])
        return s[1:]

class Integer16():
    def __init__(self):
        self.value = None

    def encode(self):
        return encoded(self.value, 2)

    def decode(self, s):
        self.value = decoded(s[:2])
        return s[2:]

class Integer32():
    def __init__(self):
        self.value = None

    def encode(self):
        return encoded(self.value, 4)

    def decode(self, s):
        self.value = decoded(s[:4])
        return s[4:]

class Integer48():
    def __init__(self):
        self.value = None

    def encode(self):
        return encoded(self.value, 6)

    def decode(self, s):
        self.value = s[:6].hex()
        return s[6:]

def sdecoded(s):
    return int.from_bytes(s, 'little', signed=True)

class SInteger8():
    def __init__(self):
        self.value = None

    def decode(self, s):
        self.value = sdecoded(s[:1])
        return s[1:]

class Opaque():
    def __init__(self):
        self.value = None

    def encode(self):
        return self.value.encode('utf-8')

class wsmp_hle():
    def __init__(self):
        self.wsmp_version = Integer8()
        self.channel_no = Integer8()
        self.data_rate = Integer8()
        self.tx_pow_level = SInteger8()
        self.channel_load = Integer8()
        self.user_priority = Integer8()
        self.peer_mac_addr = Integer48()
        self.psid = Integer32()
        self.dlen = Integer16()
        self.data = None

    def decode(self, s):
        ret_ver = self.wsmp_version.decode(s)
        ret_chh = self.channel_no.decode(ret_ver)
        ret_dr = self.data_rate.decode(ret_chh)
        ret_txpow = self.tx_pow_level.decode(ret_dr)
        ret_chld = self.channel_load.decode(ret_txpow)
        ret_usr_prio = self.user_priority.decode(ret_chld)
        ret_peer = self.peer_mac_addr.decode(ret_usr_prio)
        ret_psid = self.psid.decode(ret_peer)
        ret_len = self.dlen.decode(ret_psid)
        self.data = ret_len[:self.dlen.value]

def getPositionData(gps):
    nx = gpsd.next()
    if nx['class'] == 'TPV':
        latitude = getattr(nx, 'lat', 'Unknown')
        longitude = getattr(nx, 'lon', 'Unknown')
        speed = getattr(nx, 'speed', 'unknown')
        gps_data = [latitude, longitude, speed]
        return gps_data

gpsd = gps(mode=WATCH_ENABLE | WATCH_NEWSTYLE)

def get_cartesian(lat=None, lon=None):
    lat, lon = math.radians(lat), math.radians(lon)
    R = 6371  # radius of the earth
    x = R * math.cos(lat) * math.cos(lon)
    y = R * math.cos(lat) * math.sin(lon)
    z = R * math.sin(lat)
    return x, y, z

def distance(x1, y1, z1, x2, y2, z2):
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2 + (z2 - z1) ** 2)

def Wme_operation():
    wme_context = zmq.Context()
    wme_socket = wme_context.socket(zmq.REQ)
    wme_socket.connect("tcp://localhost:9999")

    class Action(Enum):
        Add = 1
        Delete = 2

    class wme_sub():
        def __init__(self):
            self.action = Integer8()
            self.psid = Integer32()
            self.appname = Opaque()

        def encode(self):
            out = self.action.encode() + self.psid.encode() + self.appname.encode()
            return out

    psid_sub_mag = wme_sub()
    psid_sub_mag.action.value = Action.Add.value
    psid_sub_mag.psid.value = 32
    psid_sub_mag.appname.value = "RX_APPLICATION"
    out = psid_sub_mag.encode()
    wme_socket.send(out)
    cmh_recv_msg = wme_socket.recv()
    print("psid 32 subscribed to wme")

def Wsmp_operation():
    wsmp_context = zmq.Context()
    wsmp_socket = wsmp_context.socket(zmq.SUB)
    wsmp_socket.connect("tcp://localhost:4444")
    wsmp_socket.setsockopt(zmq.SUBSCRIBE, b"32")
   
    z_lat = 17.602347
    z_lon = 78.127117

    while True:
        message = wsmp_socket.recv()
        if message != b'32':
            gps_data = getPositionData(gpsd)
            if gps_data is not None:
                latitude_self = gps_data[0]
                longitude_self = gps_data[1]
                speed_self = gps_data[2]
                z_x, z_y, z_z = get_cartesian(z_lat, z_lon)
                x_self, y_self, z_self = get_cartesian(latitude_self, longitude_self)
                dist = distance(x_self, y_self, z_self, z_x, z_y, z_z)
               
                print("Communicating with RSU: ")
                rx = message.decode('utf-8', errors='ignore')
                print("Decoded:", rx)
               
                # Save received data to file
                with open("OBU_RX.txt", "a") as file1:
                    # Parse received data
                    pairs = rx.split(',')
                    detected = '0'
                    for pair in pairs:
                        key, value = pair.split(':')
                        if key == 'Detected':
                            detected = value
                           
                    # Log detection status
                    if int(detected) > 0:
                        file1.write(rx + " Pedestrian Detected\n")
                        print("PEDESTRIAN DETECTED")
                    else:
                        file1.write(rx + " No Pedestrian Detected\n")
                        print("NO PEDESTRIAN DETECTED")
               
                # Decode WSMP message
                wsmp_msg = wsmp_hle()
                wsmp_msg.decode(message)

if __name__ == "__main__":
    Wme_operation()
    Wsmp_operation_th = threading.Thread(target=Wsmp_operation)
    Wsmp_operation_th.start()
