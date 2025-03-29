import asyncio
from bleak import BleakClient, BleakError
import time

BLE_NUS_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"  # BLE UUID
NUS_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"   # Write characteristic UUID
NUS_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"   # Notify characteristic UUID

BLE_GATT_WRITE_LEN = 20  # Max length for GATT write operations

class BLEConfigurator:
    """
    BLE Configurator for gyroscope calibration.
    """

    def __init__(self, address):
        self.address = address
        self.response_log = []
        self.commands = [
            "crt",                  
            "-f l",                 
            "-l 1 21.bin",        
            "actse 54 100"          
        ]
        self.gyro_ranges = [125, 250, 500, 1000]
        self.gyro_accuracy = 0
        self.gyro_calibration_start_time = None
        self.gyro_calibration_end_time = None

    async def nus_data_rcv_handler(self, sender, data):
        """
        Handle incoming notifications from the BLE device.
        """
        decoded_data = data.decode('utf-8').strip()
        print(f"[Received from {sender}]: {decoded_data}")
        self.response_log.append(decoded_data)
        if "Gyro Accuracy" in decoded_data:
            try:
                accuracy = int(decoded_data.split()[-1])
                if accuracy == 1 and self.gyro_calibration_start_time is None:
                    self.gyro_calibration_start_time = time.time()
                    print("Gyroscope calibration started...")
                elif accuracy == 3 and self.gyro_calibration_start_time is not None:
                    self.gyro_calibration_end_time = time.time()
                    calibration_time = self.gyro_calibration_end_time - self.gyro_calibration_start_time
                    print(f"Gyroscope calibration completed in {calibration_time:.2f} seconds.")
                self.gyro_accuracy = accuracy
            except ValueError:
                pass

    async def send_command(self, client, command):
        """
        Send a single command to the BLE device.
        """
        print(f"[Sending to {self.address[-5:]}]: {command}")
        if len(command) <= BLE_GATT_WRITE_LEN:
            await client.write_gatt_char(NUS_RX_UUID, (command + '\n').encode())
        else:
            for i in range(0, len(command), BLE_GATT_WRITE_LEN):
                await client.write_gatt_char(NUS_RX_UUID, command[i:i + BLE_GATT_WRITE_LEN].encode())
        await asyncio.sleep(0.5)

    async def wait_for_gyro_calibration(self):
        """
        Wait until the gyroscope calibration completes (Gyro Accuracy reaches 3).
        """
        print("Waiting for gyroscope calibration to complete...")
        while self.gyro_accuracy < 3:
            await asyncio.sleep(1)
        print("Gyroscope calibration completed!")

    async def configure_device(self, client):
        """
        Send configuration commands to the BLE device.
        """
        for command in self.commands:
            await self.send_command(client, command)
        print("Basic configuration commands sent.")
        await self.wait_for_gyro_calibration()
        for range_value in self.gyro_ranges:
            command = f"gconf {range_value} 2 2"
            await self.send_command(client, command)
            await asyncio.sleep(2)
            expected_response = f"Gyro Range set to {range_value}DPS"
            if any(expected_response in log for log in self.response_log):
                print(f"Response matched: {expected_response}")
            else:
                print(f"Expected response not received: {expected_response}")
                return
        print("PASS.")

    async def run(self):
        """
        Main function to connect to the BLE device, send commands, and verify responses.
        """
        client = BleakClient(self.address)
        try:
            await client.connect()
            if client.is_connected:
                print(f"Connected to {self.address[-5:]} ({self.address})")
                await client.start_notify(NUS_TX_UUID, self.nus_data_rcv_handler)
                print("Sending configuration commands...")
                await self.configure_device(client)
        except BleakError as e:
            print(f"Error connecting to {self.address}: {e}")
        finally:
            if client.is_connected:
                await client.stop_notify(NUS_TX_UUID)
                await client.disconnect()
                print(f"Disconnected from {self.address[-5:]}.")

if __name__ == "__main__":
    BLE_MAC_ADDRESS = "C4:13:E5:CD:37:72"  
    configurator = BLEConfigurator(BLE_MAC_ADDRESS)
    try:
        asyncio.run(configurator.run())
    except asyncio.CancelledError:
        print("Configuration process was interrupted.")
