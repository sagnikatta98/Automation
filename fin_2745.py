import asyncio
import os
import re
import subprocess
import pandas as pd
import plotly.graph_objects as go
from bleak import BleakClient, BleakError

BLE_NUS_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"  # BLE UUID
NUS_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # Write characteristic UUID
NUS_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # Notify characteristic UUID
BLE_GATT_WRITE_LEN = 20  # Max length for GATT write operations

class BLEHandler:
    def __init__(self, address):
        self.address = address
        self.client = BleakClient(self.address)
        self.accel_calibration_complete = False
        self.response_log = []
        self.output_dir = "output"
        os.makedirs(self.output_dir, exist_ok=True)

    async def nus_data_rcv_handler(self, sender, data):
        try:
            decoded_data = data.decode('utf-8').strip()
            print(f"[Received]: {decoded_data}")
            self.response_log.append(decoded_data)
            if "Accel Accuracy" in decoded_data:
                accuracy = int(decoded_data.split()[-1])
                if accuracy == 3:
                    print("Accelerometer calibration complete.")
                    self.accel_calibration_complete = True
        except:
            print("Received binary data (not UTF-8). Processing as raw bytes.")
            decoded_data = data.hex()
            print(f"Hex representation: {decoded_data}")
        return decoded_data

    async def send_command(self, command):
        print(f"[Sending]: {command}")
        await self.client.write_gatt_char(NUS_RX_UUID, (command + '\n').encode())
        await asyncio.sleep(0.5)

    async def log_data(self):
        try:
            await self.client.connect()
            print("Connected to device.")
            await self.client.start_notify(NUS_TX_UUID, self.nus_data_rcv_handler)
            await self.send_command("crt")
            await self.send_command("-f l")
            await self.send_command("-l 1 jj.bin")
            await self.send_command("actse 52 100")
            print("Perform accelerometer calibration by keeping each side of device stable for 3-4sec...")
            await asyncio.sleep(20)
            while not self.accel_calibration_complete:
                await asyncio.sleep(1)
            await self.send_command("-l 0")
            print("Logging stopped.")
        except BleakError as e:
            print(f"Error: {e}")

    async def read_large_binary_file(self, file_name, max_size_mb=10):
        max_size_bytes = max_size_mb * 1024 * 1024
        local_path = os.path.join(self.output_dir, file_name)
        file_data = bytearray()

        def notification_handler(sender, data):
            nonlocal file_data
            decoded_data = data.decode(errors="ignore").strip()
            if not decoded_data.startswith(("rd", "Executing rd")):
                file_data.extend(data)
                print(f"Received {len(data)} bytes of file data. Total: {len(file_data)} bytes.")
            else:
                print(f"Filtered out log message: {decoded_data}")
        print(f"Requesting file {file_name} from BLE device...")
        await self.client.start_notify(NUS_TX_UUID, notification_handler)
        await self.client.write_gatt_char(NUS_RX_UUID, f"rd {file_name}\n".encode())
        timeout = 30
        for _ in range(timeout):
            await asyncio.sleep(1)
            if len(file_data) >= max_size_bytes:
                print(f"File transfer limit of {max_size_mb} MB reached. Stopping...")
                break
        await self.client.stop_notify(NUS_TX_UUID)
        with open(local_path, "wb") as f:
            f.write(file_data)
        print(f"File saved to {local_path} ({len(file_data)} bytes received)")
        return local_path

    def clean_bin_file(self, bin_file):
        print(f"Cleaning binary file: {bin_file}...")
        with open(bin_file, "rb") as f:
            content = f.read()
        decoded_content = content.decode(errors="ignore")
        match = re.search(r"1\.0\s*\n1:\s*Accelerometer.*?\n", decoded_content, re.DOTALL)
        if match:
            valid_start = match.start()
            valid_content = content[valid_start:]
            with open(bin_file, "wb") as f:
                f.write(valid_content)
            print("Binary file cleaned successfully.")
        else:
            raise ValueError("Valid header not found in the binary file. File might be corrupted.")

    def convert_bin_to_csv(self, bin_file):
        csv_file = os.path.splitext(bin_file)[0] + ".bin.csv"
        exe_path = os.path.join(os.getcwd(), "udf2csv.exe")
        if not os.path.exists(exe_path):
            raise FileNotFoundError(f"udf2csv.exe not found in {os.getcwd()}")
        print(f"Converting {bin_file} to CSV using {exe_path}...")
        try:
            result = subprocess.run([exe_path, bin_file], capture_output=True, text=True)
            if result.returncode != 0:
                print(f"Error during conversion: {result.stderr}")
                raise RuntimeError("Failed to convert .bin to .csv")
            print(f"CSV file created: {csv_file}")
            return csv_file
        except Exception as e:
            print(f"Error during conversion: {e}")
            raise

    def validate_csv(self, csv_file):
        """Validate the contents of the CSV file by loading it into a DataFrame"""
        print(f"Reading {csv_file} into a dataframe...")
        df = pd.read_csv(csv_file)
        df.columns = df.columns.str.strip()
        column_name = "Accel Corrected 0.a"
        df[column_name] = pd.to_numeric(df[column_name], errors="coerce")       
        if column_name in df.columns:
            print(f"Generating HTML plot for {column_name}...")
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df.index, 
                y=df[column_name],
                mode='lines',
                name=column_name,
                line=dict(color='blue')
            ))
            fig.update_layout(
                title="2D Plot of Accel Corrected 0.a",
                xaxis_title="Index",
                yaxis_title="Accel Corrected 0.a",
                template="plotly_white"
            )
            first_reach_3 = df[df[column_name] == 3].index.min()
            accuracy_drops = df.loc[first_reach_3:, column_name].isin([0, 1, 2]).any()
            if first_reach_3 is not None and not accuracy_drops:
                pass_status = "PASS"
            else:
                pass_status = "FAIL"
            html_file = "accel_corrected_plot_2745.html"
            with open(html_file, "w") as f:
                f.write(fig.to_html(full_html=False, include_plotlyjs='cdn'))
                f.write(f"<h2>Test Status: {pass_status}</h2>")
            print(f"Plot saved as {html_file} with test result: {pass_status}.")
        else:
            print(f"Column '{column_name}' or '{column_name}' not found in the CSV file.")
        return df

    async def run(self):
        try:
            await self.log_data()
            bin_file = await self.read_large_binary_file("jj.bin")
            self.clean_bin_file(bin_file)
            csv_file = self.convert_bin_to_csv(bin_file)
            self.validate_csv(csv_file)
        except BleakError as e:
            print(f"Error: {e}")
        finally:
            if self.client.is_connected:
                await self.client.disconnect()
                print("Disconnected from device.")

if __name__ == "__main__":
    BLE_MAC_ADDRESS = "FE:5F:42:38:8C:C0"
    handler = BLEHandler(BLE_MAC_ADDRESS)
    try:
        asyncio.run(handler.run())
    except asyncio.CancelledError:
        print("Process interrupted.")
