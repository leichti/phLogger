import json
import sys
import serial
import serial.tools.list_ports
import pandas as pd
import re
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                             QComboBox, QPushButton, QLineEdit, QTextEdit, QFileDialog, QSpinBox)
from PyQt5.QtCore import QThread, pyqtSignal, QDateTime
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import time
import os


class SerialReader(QThread):
    data_received = pyqtSignal(str, float)

    def __init__(self, port, baudrate, initial_timestamp):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.running = True
        self.initial_timestamp = initial_timestamp

    def run(self):
        try:
            with serial.Serial(self.port, self.baudrate) as ser:
                while self.running:
                    if ser.in_waiting:
                        data = ser.readline().decode('utf-8', errors='replace').strip()
                        match = re.search(r'(\d+\.\d+)pH', data)
                        if match:
                            ph_value = float(match.group(1))
                            current_timestamp = time.time()
                            elapsed_time = (
                                                       current_timestamp - self.initial_timestamp) / 60  # minutes since initial timestamp
                            self.data_received.emit(data, elapsed_time)
                        time.sleep(1)
        except serial.SerialException as e:
            self.data_received.emit(f"Error: {e}", 0)

    def stop(self):
        self.running = False


class AppWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle('COM Port Reader with Matplotlib Plot')
        self.setGeometry(100, 100, 1200, 600)

        self.main_layout = QHBoxLayout()

        self.settings_frame = QWidget()
        self.plot_frame = QWidget()

        self.main_layout.addWidget(self.settings_frame)
        self.main_layout.addWidget(self.plot_frame)

        self.settings_layout = QVBoxLayout()
        self.settings_frame.setLayout(self.settings_layout)

        self.plot_layout = QVBoxLayout()
        self.plot_frame.setLayout(self.plot_layout)

        self.init_settings_ui()
        self.init_plot()

        container = QWidget()
        container.setLayout(self.main_layout)
        self.setCentralWidget(container)

        self.serial_thread = None
        self.data = pd.DataFrame(columns=['Timestamp', 'Elapsed Time (min)', 'pH'])
        self.start_time = None

        self.load_settings()

    def load_settings(self):
        try:
            with open('settings.json', 'r') as file:
                settings = json.load(file)
                self.com_ports.setCurrentText(settings.get('com_port', ''))
        except FileNotFoundError:
            pass

    def save_settings(self):
        settings = {
            'com_port': self.com_ports.currentText()
        }
        with open('settings.json', 'w') as file:
            json.dump(settings, file)

    def stop_and_save(self):
        self.stop_reading()
        self.save_settings()
        self.close()

    def init_settings_ui(self):
        # COM Port selection
        self.com_label = QLabel("Select COM Port:")
        self.settings_layout.addWidget(self.com_label)
        self.com_ports = QComboBox()
        self.update_com_ports()
        self.settings_layout.addWidget(self.com_ports)

        # Baudrate selection
        self.baudrate_label = QLabel("Select Baudrate:")
        self.settings_layout.addWidget(self.baudrate_label)
        self.baudrate = QComboBox()
        self.baudrate.addItems(['1200', '2400', '4800', '9600', '19200', '38400', '57600', '115200'])
        self.baudrate.setCurrentText('1200')
        self.settings_layout.addWidget(self.baudrate)

        # Output directory
        self.dir_button = QPushButton('Select Output Directory')
        self.dir_button.clicked.connect(self.select_output_directory)
        self.settings_layout.addWidget(self.dir_button)

        self.dir_path = QLineEdit()
        self.settings_layout.addWidget(self.dir_path)

        # Filename
        self.filename_label = QLabel("Enter Filename:")
        self.settings_layout.addWidget(self.filename_label)
        self.filename = QLineEdit()
        self.settings_layout.addWidget(self.filename)

        # Static settings display
        self.settings_layout.addWidget(QLabel("Data Bits: 8"))
        self.settings_layout.addWidget(QLabel("Stop Bits: 1"))
        self.settings_layout.addWidget(QLabel("Parity: None"))
        self.settings_layout.addWidget(QLabel("Flow Control: None"))

        # Logging console
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.settings_layout.addWidget(self.console)

        # Start reading button
        self.start_button = QPushButton('Start Reading')
        self.start_button.clicked.connect(self.start_reading)
        self.settings_layout.addWidget(self.start_button)

        # Stop reading button
        self.stop_button = QPushButton('Stop Reading')
        self.stop_button.clicked.connect(self.stop_reading)
        self.settings_layout.addWidget(self.stop_button)

        # Reset button
        self.reset_button = QPushButton('Reset')
        self.reset_button.clicked.connect(self.reset)
        self.settings_layout.addWidget(self.reset_button)

        # Stop and Save button
        self.stop_and_save_button = QPushButton('Stop and Save')
        self.stop_and_save_button.clicked.connect(self.stop_and_save)
        self.settings_layout.addWidget(self.stop_and_save_button)

        # X-axis limit controls
        self.settings_layout.addWidget(QLabel("X-axis min:"))
        self.xmin_spinbox = QSpinBox()
        self.xmin_spinbox.setRange(0, 1000)
        self.xmin_spinbox.valueChanged.connect(self.update_plot_limits)
        self.settings_layout.addWidget(self.xmin_spinbox)

        self.settings_layout.addWidget(QLabel("X-axis max:"))
        self.xmax_spinbox = QSpinBox()
        self.xmax_spinbox.setRange(0, 1000)
        self.xmax_spinbox.setValue(60)  # default to 60 minutes
        self.xmax_spinbox.valueChanged.connect(self.update_plot_limits)
        self.settings_layout.addWidget(self.xmax_spinbox)

        # Y-axis limit controls
        self.settings_layout.addWidget(QLabel("Y-axis min:"))
        self.ymin_spinbox = QSpinBox()
        self.ymin_spinbox.setRange(0, 14)
        self.ymin_spinbox.setValue(0)
        self.ymin_spinbox.valueChanged.connect(self.update_plot_limits)
        self.settings_layout.addWidget(self.ymin_spinbox)

        self.settings_layout.addWidget(QLabel("Y-axis max:"))
        self.ymax_spinbox = QSpinBox()
        self.ymax_spinbox.setRange(0, 14)
        self.ymax_spinbox.setValue(14)
        self.ymax_spinbox.valueChanged.connect(self.update_plot_limits)
        self.settings_layout.addWidget(self.ymax_spinbox)

    def init_plot(self):
        self.figure, self.ax = plt.subplots()
        self.canvas = FigureCanvas(self.figure)
        self.plot_layout.addWidget(self.canvas)
        self.ax.set_xlabel('Time (minutes)')
        self.ax.set_ylabel('pH Value')

    def update_plot_limits(self):
        self.ax.set_xlim(self.xmin_spinbox.value(), self.xmax_spinbox.value())
        self.ax.set_ylim(self.ymin_spinbox.value(), self.ymax_spinbox.value())
        self.canvas.draw()

    def update_com_ports(self):
        ports = serial.tools.list_ports.comports()
        self.com_ports.clear()
        self.com_ports.addItems([port.device for port in ports])

    def select_output_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Directory")
        if directory:
            self.dir_path.setText(directory)

    def start_reading(self):
        port = self.com_ports.currentText()
        baudrate = self.baudrate.currentText()
        if port and baudrate:
            if self.start_time is None:
                self.start_time = time.time()
            self.serial_thread = SerialReader(port, baudrate, self.start_time)
            self.serial_thread.data_received.connect(self.process_data)
            self.serial_thread.start()

    def closeEvent(self, event):
        self.save_settings()
        event.accept()

    def stop_reading(self):
        if self.serial_thread:
            self.serial_thread.stop()
            self.serial_thread.wait()

    def reset(self):
        self.stop_reading()

        # Clear DataFrame, reset start time, and clear plot
        self.data = pd.DataFrame(columns=['Timestamp', 'Elapsed Time (min)', 'pH'])
        self.start_time = None
        self.console.clear()
        self.ax.clear()
        self.ax.set_xlabel('Time (minutes)')
        self.ax.set_ylabel('pH Value')
        self.canvas.draw()

    def process_data(self, data, elapsed_time):
        self.console.append(data)
        timestamp = QDateTime.currentDateTime().toString()
        ph_value = float(re.search(r'(\d+\.\d+)pH', data).group(1))

        # Append data to DataFrame using concat
        new_row = pd.DataFrame({'Timestamp': [timestamp], 'Elapsed Time (min)': [elapsed_time], 'pH': [ph_value]})
        self.data = pd.concat([self.data, new_row], ignore_index=True)

        # Append data to CSV file
        output_directory = self.dir_path.text()
        filename = self.filename.text()
        if output_directory and filename:
            csv_path = f"{output_directory}/{filename}.csv"
            if not os.path.isfile(csv_path):
                self.data.to_csv(csv_path, index=False)
            else:
                new_row.to_csv(csv_path, mode='a', header=False, index=False)

        # Update plot
        self.ax.clear()
        self.ax.plot(self.data['Elapsed Time (min)'], self.data['pH'])
        self.ax.set_xlabel('Time (minutes)')
        self.ax.set_ylabel('pH Value')
        self.update_plot_limits^()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AppWindow()
    window.show()
    sys.exit(app.exec_())