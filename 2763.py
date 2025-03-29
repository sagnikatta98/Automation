import asyncio 
from bleak import BleakClient, BleakError
import time

BLE_NUS_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e" # BLE UUID
NUS_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # Write characteristic UUID
NUS_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # Notify characteristic UUID

SENSOR_NAMES = ["GYRO_CRCTD_X_Y_Z","Gravity_X_Y_Z:", "Linear_Acc_X_Y_Z:","ACC_CRCTD_X_Y_Z:","GYR_PASSTHRO_X_Y_Z_A:","ACCEL_RAW_X_Y_Z_A:"]

class BLEConfigurator:
    def __init__(self, address):
        self.address = address
        self.response_log = [] 
        self.client = None
        self.sensor_data_present = set()
    
    async def nus_data_rcv_handler(self, sender, data):
        decoded_data = data.decode('utf-8').strip()
        print(f"[Received]: {decoded_data}")
        self.response_log.append(decoded_data)
        for sensor in SENSOR_NAMES:
            if sensor in decoded_data:
                self.sensor_data_present.add(sensor)

    async def send_command(self, command):
        print(f"[Sending]: {command}")
        await self.client.write_gatt_char(NUS_RX_UUID, (command + '\n').encode())
        await asyncio.sleep(0.5)

    async def run(self):
        self.client = BleakClient(self.address)
        try:
            await self.client.connect()
            print("Connected to device.")
            await self.client.start_notify(NUS_TX_UUID, self.nus_data_rcv_handler)
            await self.send_command("crt")
            await self.send_command("-f l")
            for cmd in ["actse 52 50","actse 54 50", "actse 15 50", "actse 17 50", "actse 64 50", "actse 72 50"]:
                await self.send_command(cmd)
            await self.send_command("-a 1")
            await asyncio.sleep(15)
            if all(sensor in self.sensor_data_present for sensor in SENSOR_NAMES):
                print("PASS: All expected sensors are streaming data.")
            else:
                print("FAIL: Some sensors are missing from the stream.")
            await self.send_command("-a 0")
            print("Disconnecting device...")
        except BleakError as e:
            print(f"Error: {e}")
        finally:
            if self.client.is_connected:
                await self.client.stop_notify(NUS_TX_UUID)
                await self.client.disconnect()
                print("Disconnected.")

if __name__ == "__main__":
    BLE_MAC_ADDRESS = "C4:13:E5:CD:37:72"
    configurator = BLEConfigurator(BLE_MAC_ADDRESS)
    try:
        asyncio.run(configurator.run())
    except asyncio.CancelledError:
        print("Process interrupted.")
