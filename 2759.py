import asyncio  
from bleak import BleakClient, BleakError
import time

BLE_NUS_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUS_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

BLE_GATT_WRITE_LEN = 20
RECONNECT_ATTEMPTS = 5

class BLEConfigurator:
    def __init__(self, address):
        self.address = address
        self.response_log = []
        self.client = None
        self.gyro_calibration_complete = False
        self.accel_calibration_complete = False
        self.accuracy_info_received = False

    async def nus_data_rcv_handler(self, sender, data):
        decoded_data = data.decode('utf-8').strip()
        print(f"[Received]: {decoded_data}")
        self.response_log.append(decoded_data)
        if "Gyro Accuracy" in decoded_data or "Accel Accuracy" in decoded_data:
            self.accuracy_info_received = True
        if "Gyro Accuracy" in decoded_data and int(decoded_data.split()[-1]) == 3:
            self.gyro_calibration_complete = True
        if "Accel Accuracy" in decoded_data and int(decoded_data.split()[-1]) == 3:
            self.accel_calibration_complete = True

    async def send_command(self, command):
        print(f"[Sending]: {command}")
        await self.client.write_gatt_char(NUS_RX_UUID, (command + '\n').encode())
        await asyncio.sleep(0.5)

    async def connect_and_configure(self):
        self.client = BleakClient(self.address)
        try:
            await self.client.connect()
            print("Connected to device.")
            await self.client.start_notify(NUS_TX_UUID, self.nus_data_rcv_handler)
            await self.send_command("crt")
            await self.send_command("-f l") 
            await self.send_command("actse 54 100")
            await self.send_command("actse 52 100")
            return True
        except BleakError as e:
            print(f"Error: {e}")
            return False

    async def disconnect_device(self):
        try:
            if self.client and self.client.is_connected:
                await self.client.stop_notify(NUS_TX_UUID)
                await self.client.disconnect()
                print("Disconnected successfully.")
        except Exception as e:
            print(f"Error during disconnection: {e}")

    async def run(self):
        if not await self.connect_and_configure():
            return
        print("Gyroscope and accelerometer calibration started....")
        while not self.gyro_calibration_complete:
            await asyncio.sleep(1)
        while not self.accel_calibration_complete:
            await asyncio.sleep(1)
        await asyncio.sleep(5)
        print("Calibration complete. Disconnecting device...")
        await self.disconnect_device()

        for i in range(RECONNECT_ATTEMPTS):
            print(f"Reconnecting attempt {i+1}...")
            self.accuracy_info_received = False
            if not await self.connect_and_configure():
                print("Reconnection failed. Retrying...")
                await asyncio.sleep(2)
                continue
            await asyncio.sleep(3)
            await self.disconnect_device()
            if not self.accuracy_info_received:
                print("PASS: Accuracy remained at 3.")
            else:
                print("FAIL: Accuracy info received unexpectedly.")

if __name__ == "__main__":
    BLE_MAC_ADDRESS = "C4:13:E5:CD:37:72"
    configurator = BLEConfigurator(BLE_MAC_ADDRESS)
    try:
        asyncio.run(configurator.run())
    except asyncio.CancelledError:
        print("Process interrupted.")