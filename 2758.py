import asyncio 
from bleak import BleakClient, BleakError
import time

BLE_NUS_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e" # BLE UUID
NUS_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # Write characteristic UUID
NUS_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # Notify characteristic UUID

SENSOR_NAMES = ["Orient_H_P_R:","Gravity_X_Y_Z:", "Linear_Acc_X_Y_Z:","ACC_CRCTD_X_Y_Z:"]
DISABLED_SENSORS = {"Linear_Acc_X_Y_Z:", "Gravity_X_Y_Z:", "ACC_CRCTD_X_Y_Z:", "Orient_H_P_R:"}

class BLEConfigurator:
    def __init__(self, address):
        self.address = address
        self.response_log = [] 
        self.client = None
        self.gyro_calibration_complete = False
        self.accel_calibration_complete = False
        self.gyro_calibration_start_time = None
        self.gyro_calibration_end_time = None
        self.sensor_data_present = set()
    
    async def nus_data_rcv_handler(self, sender, data):
        decoded_data = data.decode('utf-8').strip()
        print(f"[Received]: {decoded_data}")
        self.response_log.append(decoded_data)
        for sensor in SENSOR_NAMES:
            if sensor in decoded_data:
                self.sensor_data_present.add(sensor)
        if "Gyro Accuracy" in decoded_data:
            accuracy = int(decoded_data.split()[-1])
            if accuracy == 1 and self.gyro_calibration_start_time is None:
                self.gyro_calibration_start_time = time.time()
            if accuracy == 3:
                self.gyro_calibration_end_time = time.time()
                self.gyro_calibration_complete = True
                calibration_time = self.gyro_calibration_end_time - self.gyro_calibration_start_time
                print(f"Gyroscope calibration complete. Time taken: {calibration_time:.2f} seconds.")
        if "Accel Accuracy" in decoded_data:
            accuracy = int(decoded_data.split()[-1])
            if accuracy == 3:
                print("Accelerometer calibration complete.")
                self.accel_calibration_complete = True

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
            for cmd in ["actse 13 50","actse 15 50", "actse 17 50", "actse 52 50"]:
                await self.send_command(cmd)
            print("Waiting 15 seconds for gyro calibration...")
            await asyncio.sleep(15)
            while not self.gyro_calibration_complete:
                await asyncio.sleep(1)
            print("Perform accel calibration by keeping each side of device stable for 3-4sec...")
            while not self.accel_calibration_complete:
                await asyncio.sleep(1)
            await self.send_command("-a 1")
            if all(sensor in self.sensor_data_present for sensor in SENSOR_NAMES):
                print("PASS: All expected sensors are streaming data.")
            else:
                print("FAIL: Some sensors are missing from the stream.")
            for cmd in ["actse 13 0", "actse 15 0", "actse 17 0", "actse 52 0"]:
                await self.send_command(cmd)
            self.sensor_data_present.clear()
            await asyncio.sleep(10)
            if all(sensor not in self.sensor_data_present for sensor in DISABLED_SENSORS):
                print("PASS: Disabled sensors are no longer streaming data.")
            else:
                print("FAIL: Some disabled sensors are still present in the stream.")
            await self.send_command("-l 0")
            print("Logging stopped. Disconnecting device...")
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
