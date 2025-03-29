import asyncio 
from bleak import BleakClient, BleakError
import time

BLE_NUS_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e" # BLE UUID
NUS_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # Write characteristic UUID
NUS_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # Notify characteristic UUID

BLE_GATT_WRITE_LEN = 20  # Max length for GATT write operations

class BLEConfigurator:
    """
    BLE Configurator for gyroscope calibration with user guidance via pop-up.
    """

    def __init__(self, address):
        self.address = address
        self.response_log = [] 
        self.popup_root = None
        self.commands = [
            "crt",                  # Command to trigger crt
            "-f l",                 # Command to enable ImuX
            "-l 1 mop.bin",
            "actse 52 100",         # Command to create log file
            "actse 54 100"          # Command to activate gyroscope corrected sensor
        ]
        self.gyro_calibration_start_time = None
        self.gyro_calibration_end_time = None
        self.accel_calibration_complete = False
        self.gyro_calibration_complete = False
        self.stop_logging = False

    async def nus_data_rcv_handler(self, sender, data):
        """
        Handle incoming notifications from the BLE device.
        """
        decoded_data = data.decode('utf-8').strip()
        print(f"[Received from {sender}]: {decoded_data}")
        self.response_log.append(decoded_data)
        
        if "Accel Accuracy" in decoded_data:
            accuracy = int(decoded_data.split()[-1])
            if accuracy == 1:
                print("Accel accuracy 1 reached. Place each axis of the device flat on the table for 3-4 seconds.")
            elif accuracy == 3:
                print("Accel accuracy 3 reached. Calibration complete.")
                self.accel_calibration_complete = True

        # Checking for gyroscope calibration accuracy and track time
        if "Gyro Accuracy" in decoded_data:
            accuracy = int(decoded_data.split()[-1])
            if accuracy == 1 and self.gyro_calibration_start_time is None:
                # Recorded start time when Gyro Accuracy reaches 1
                self.gyro_calibration_start_time = time.time()
                print("Gyroscope calibration started...")
            elif accuracy == 3 and self.gyro_calibration_start_time is not None:
                # Recorded end time when Gyro Accuracy reaches 3
                self.gyro_calibration_end_time = time.time()
                calibration_time = self.gyro_calibration_end_time - self.gyro_calibration_start_time
                print(f"Gyroscope calibration completed. Time taken: {calibration_time:.2f} seconds.")
                self.gyro_calibration_start_time = None
                self.gyro_calibration_complete = True

        if self.accel_calibration_complete and self.gyro_calibration_complete:
            print("Waiting 10 seconds before logging is stopped")
            await asyncio.sleep(10)
            await self.send_command(self.client, "-l 0")
            print("Disconnecting device...")
            await self.disconnect_device()
        return

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
        
        # Waiting briefly to allow the BLE device to process and respond
        await asyncio.sleep(0.5)

    async def configure_device(self, client):
        """
        Send configuration commands to the BLE device.
        """
        for command in self.commands:
            await self.send_command(client, command)

    async def continuous_stream(self, client):
        """
        Enter continuous streaming mode and handle incoming data indefinitely.
        """
        print(f"Entering continuous receive mode for {self.address[-5:]}")
        try:
            while True:
                await asyncio.sleep(5)  # loop running to receive notifications
        except asyncio.CancelledError:
            print("Continuous receive mode interrupted.")
    
    async def disconnect_device(self):
        """
        Stop notifications and disconnect the BLE device.
        """
        if self.client and self.client.is_connected:
            await self.client.stop_notify(NUS_TX_UUID)
            await self.client.disconnect()
            print(f"Disconnected from {self.address[-5:]}.")
    

    async def run(self):
        """
        Main function to connect to the BLE device, send commands, and stream data.
        """
        self.client = BleakClient(self.address)
        try:
            await self.client.connect()
            if self.client.is_connected:
                print(f"Connected to {self.address[-5:]} ({self.address})")

                # Starting to receiving notifications
                await self.client.start_notify(NUS_TX_UUID, self.nus_data_rcv_handler)

                # Sending configuration commands
                print("Sending configuration commands...")
                await self.configure_device(self.client)

                # Entering continuous streaming mode
                await self.continuous_stream(self.client)

        except BleakError as e:
            print(f"Error connecting to {self.address}: {e}")
        finally:
            if self.client.is_connected:
                await self.client.stop_notify(NUS_TX_UUID)
                await self.client.disconnect()
                print(f"Disconnected from {self.address[-5:]}.")

if __name__ == "__main__":

    # BLE device MAC address
    BLE_MAC_ADDRESS = "F3:D9:31:80:1B:0B"  

    configurator = BLEConfigurator(BLE_MAC_ADDRESS)
    try:
        asyncio.run(configurator.run())
    except asyncio.CancelledError:
        print("Configuration process was interrupted.")
