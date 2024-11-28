import threading
import zmq
import time
import csv
import math
from enum import Enum
from gps import *
from geopy.geocoders import Nominatim
import requests

#### Define Enumerations and Data Structures ####

class Results(Enum):
    Failure = 0
    Success = 1

def decoded(s):
    return int.from_bytes(s, 'little')

def encoded(value, length, signed=False):
    return value.to_bytes(length, 'little', signed=signed)

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

class SInteger8():
    def __init__(self):
        self.value = None

    def encode(self):
        if self.value is None:
            return None
        return encoded(self.value, 1, signed=True)

    def decode(self, s):
        self.value = int.from_bytes(s[:1], byteorder='little', signed=True)
        return s[1:]

class Integer48():
    def __init__(self):
        self.value = None

    def encode(self):
        return encoded(self.value, 6)

    def decode(self, s):
        self.value = s[:6].hex()
        return s[6:]

class Opaque():
    def __init__(self):
        self.value = None

    def encode(self):
        return self.value.encode('utf-8')

class mode(Enum):
    SPS_MODE = 1
    ADHOC_MODE = 2

class hle_wsmp():
    def __init__(self):
        self.mode = Integer8()
        self.ch_id = Integer8()
        self.time_slot = Integer8()
        self.data_rate = Integer8()
        self.tx_pow = SInteger8()
        self.ch_ld = Integer8()
        self.info = Integer8()
        self.usr_prio = Integer8()
        self.expiry_time = Integer8()
        self.mac = Integer48()
        self.psid = Integer32()
        self.dlen = Integer16()
        self.data = None

    def encode(self):
        out = (
            self.mode.encode() +
            self.ch_id.encode() +
            self.time_slot.encode() +
            self.data_rate.encode() +
            self.tx_pow.encode() +
            self.ch_ld.encode() +
            self.info.encode() +
            self.usr_prio.encode() +
            self.expiry_time.encode() +
            self.mac.encode() +
            self.psid.encode() +
            self.dlen.encode() +
            self.data
        )
        return out

def FillWsmpContent(data):
    hle_msg = hle_wsmp()
    hle_msg.mode.value = mode.SPS_MODE.value
    hle_msg.ch_id.value = 172
    hle_msg.time_slot.value = 0
    hle_msg.data_rate.value = 12
    hle_msg.tx_pow.value = -98
    hle_msg.ch_ld.value = 0
    hle_msg.info.value = 0
    hle_msg.expiry_time.value = 0
    hle_msg.usr_prio.value = 0
    hle_msg.mac.value = 16557351571215
    hle_msg.psid.value = 32
    hle_msg.dlen.value = len(data)
    hle_msg.data = bytes(data, 'utf-8')
    encoded_msg = hle_msg.encode()
   
    # Debug: Show the complete encoded message
    print("Encoded WSMP message:", encoded_msg)
   
    return encoded_msg

def getPositionData(gps):
    nx = gpsd.next()
    if nx['class'] == 'TPV':
        latitude = getattr(nx, 'lat', "Unknown")
        longitude = getattr(nx, 'lon', "Unknown")
        speed = getattr(nx, 'speed', "unknown")
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

def get_heading(aLocation):
    off_x = aLocation[-1][1] - aLocation[-2][1]
    off_y = aLocation[-1][0] - aLocation[-2][0]
    heading = 90.00 + math.atan2(-off_y, off_x) * 57.2957795
    if heading < 0:
        heading += 360.00
    return heading

def wsmp_operation():
    wsmp_context = zmq.Context()
    wsmp_socket = wsmp_context.socket(zmq.REQ)
    wsmp_socket.connect("tcp://localhost:5555")

    x1, y1, z1 = 0.0, 0.0, 0.0
    alocation = [[0, 0]]
    while True:
        file1 = open('RSU_TX.txt', "a")
        gps_data = getPositionData(gpsd)
        if gps_data is not None:
            speed = gps_data[2]
            latitude = gps_data[0]
            longitude = gps_data[1]
            alocation.append([latitude, longitude])
            head_ang = get_heading(alocation)
            x1, y1, z1 = get_cartesian(latitude, longitude)
           
            # Read the latest CSV file from the OBU
            csv_filename = '/home/guest/praneeth/person_detection.csv'
            try:
                with open(csv_filename, 'r') as file:
                    reader = csv.reader(file)
                    last_row = list(reader)[-1]  # Read the last row
                    serial_number, timestamp, detected, count, confidence_ratio = last_row
                    application_data = (
                        f"SN:{serial_number},Timestamp:{timestamp},"
                        f"Confidence ratio:{confidence_ratio},Count:{count},Detected:{detected},"
                        f"Lat:{latitude},Long:{longitude},Speed:{speed}"
                    )
                    # Debug: Show the complete application data
                    print("Application data:", application_data)
            except Exception as e:
                print(f"Error reading CSV file: {e}")
                application_data = "ERROR: Unable to read data"

            # Prepare and send WSMP message
            result = FillWsmpContent(application_data)
            wsmp_socket.send(result)
            msg = wsmp_socket.recv()
            print("Response from WSMP server:", msg)
            file1.write(application_data + "\n")
            file1.close()
        time.sleep(1)  # Adjust sleep time as needed

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
    psid_sub_mag.appname.value = "TX_APPLICATION"
    out = psid_sub_mag.encode()
    wme_socket.send(out)
    cmh_recv_msg = wme_socket.recv()
    print("psid 32 subscribed to wme")

if __name__ == "__main__":
    Wme_operation()
    app_operation_th = threading.Thread(target=wsmp_operation)
    app_operation_th.start()
