import asyncio 
from bleak import BleakClient, BleakError
import time

BLE_NUS_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e" # BLE UUID
NUS_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # Write characteristic UUID
NUS_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # Notify characteristic UUID

BLE_GATT_WRITE_LEN = 20  # Max length for GATT write operations

class BLEConfigurator:
    """
    BLE Configurator for sensor calibration.
    """

    def __init__(self, address):
        self.address = address
        self.response_log = [] 
        self.client = None
        self.gyro_calibration_complete = False
        self.accel_calibration_complete = False
        self.gyro_calibration_start_time = None
        self.gyro_calibration_end_time = None

    async def nus_data_rcv_handler(self, sender, data):
        """
        Handle incoming notifications from the BLE device.
        """
        decoded_data = data.decode('utf-8').strip()
        print(f"[Received]: {decoded_data}")
        self.response_log.append(decoded_data)
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
        """Send a single command to the BLE device."""
        print(f"[Sending]: {command}")
        await self.client.write_gatt_char(NUS_RX_UUID, (command + '\n').encode())
        await asyncio.sleep(0.5)

    async def run(self):
        """Main function to connect, configure, calibrate, and disconnect."""
        self.client = BleakClient(self.address)
        try:
            await self.client.connect()
            print("Connected to device.")
            await self.client.start_notify(NUS_TX_UUID, self.nus_data_rcv_handler)
            await self.send_command("crt")
            await self.send_command("-f l")
            await self.send_command("-l 1 2766.bin")
            await self.send_command("actse 9 100")
            print("Gyro calibration started. Keep device stable for 15 seconds")
            await asyncio.sleep(15)
            while not self.gyro_calibration_complete:
                await asyncio.sleep(1)
            print("Perform Accel calibration. Keep each side of device stable for 3-4sec...")
            while not self.accel_calibration_complete:
                await asyncio.sleep(1)
            print("Perform AR hand movements for 10sec and place device with roll axis on table...")
            await asyncio.sleep(10)
            await self.send_command("lab stable_point")
            await asyncio.sleep(10)
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
    BLE_MAC_ADDRESS = "F6:F5:4C:1F:BD:5F"
    configurator = BLEConfigurator(BLE_MAC_ADDRESS)
    try:
        asyncio.run(configurator.run())
    except asyncio.CancelledError:
        print("Process interrupted.")