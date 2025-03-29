import asyncio
from bleak import BleakClient, BleakError
import tkinter as tk
from threading import Thread
import time

BLE_NUS_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e" # BLE UUID
NUS_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # Write characteristic UUID
NUS_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # Notify characteristic UUID

BLE_GATT_WRITE_LEN = 20  # Max length for GATT write operations

class BLEConfigurator:
    """
    BLE Configurator for accelerometer and gyroscope calibration with user guidance via pop-up.
    """

    def __init__(self, address):
        self.address = address
        self.response_log = [] 
        self.popup_active = False
        self.popup_root = None
        self.commands = [
            "crt",                  # Command to trigger crt
            "-f l",                 # Command to enable ImuX
            "-l 1 qoq.bin",       # Command to create log file
            "actse 52 100",         # Command to activate accelerometer corrected sensor
            "actse 54 100"          # Command to activate gyroscope corrected sensor
        ]
        self.gyro_calibration_start_time = None
        self.gyro_calibration_end_time = None  

    def show_popup(self):
        """
        Display a pop-up to guide the user for accelerometer calibration.
        """
        self.popup_active = True
        self.popup_root = tk.Tk()
        self.popup_root.title("Accelerometer Calibration")
        self.popup_root.geometry("400x150")
        label = tk.Label(
            self.popup_root, 
            text="Place each axis of the device flat on the table for 3-4 seconds to complete calibration.",
            wraplength=350, 
            justify="center"
        )
        label.pack(expand=True)
        self.popup_root.mainloop()

    def close_popup(self):
        """
        Close the pop-up once calibration is complete.
        """
        if self.popup_active and self.popup_root:
            self.popup_root.destroy()
            self.popup_active = False

    async def nus_data_rcv_handler(self, sender, data):
        """
        Handle incoming notifications from the BLE device.
        """
        decoded_data = data.decode('utf-8').strip()
        print(f"[Received from {sender}]: {decoded_data}")
        self.response_log.append(decoded_data)

        # Checking for accelerometer calibration accuracy
        if "Gyro Accuracy" in decoded_data:
            accuracy = int(decoded_data.split()[-1])
            if accuracy == 3 and not self.popup_active:
                print("Accelerometer accuracy 1 reached. Showing calibration guidance.")
                popup_thread = Thread(target=self.show_popup)
                popup_thread.start()
        if "Accel Accuracy" in decoded_data:
            accuracy = int(decoded_data.split()[-1])
            if accuracy == 3:
                self.close_popup()

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

    async def run(self):
        """
        Main function to connect to the BLE device, send commands, and stream data.
        """
        client = BleakClient(self.address)
        try:
            await client.connect()
            if client.is_connected:
                print(f"Connected to {self.address[-5:]} ({self.address})")

                # Starting to receiving notifications
                await client.start_notify(NUS_TX_UUID, self.nus_data_rcv_handler)

                # Sending configuration commands
                print("Sending configuration commands...")
                await self.configure_device(client)

                # Entering continuous streaming mode
                await self.continuous_stream(client)

        except BleakError as e:
            print(f"Error connecting to {self.address}: {e}")
        finally:
            if client.is_connected:
                await client.stop_notify(NUS_TX_UUID)
                await client.disconnect()
                print(f"Disconnected from {self.address[-5:]}.")
            self.close_popup()

if __name__ == "__main__":

    # BLE device MAC address
    BLE_MAC_ADDRESS = "F3:D9:31:80:1B:0B"  

    configurator = BLEConfigurator(BLE_MAC_ADDRESS)
    try:
        asyncio.run(configurator.run())
    except asyncio.CancelledError:
        print("Configuration process was interrupted.")
