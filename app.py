#!/usr/bin/env python3
import subprocess
import json
import time
from flask import Flask, render_template, jsonify
import threading
import re

app = Flask(__name__)

# Store recent data points (last 60 seconds)
data_history = {
    'timestamps': [],
    'cpu_temp': [],
    'cpu_usage': [],
    'cpu_cores': [],  # Per-core usage
    'cpu_freq': [],
    'cpu_fan': [],
    'gpu_fan': [],
    'cpu_power': [],
    'gpu_temp': [],
    'gpu_power': [],
    'gpu_util': [],
    'gpu_mem_util': [],
    'gpu_mem_used': [],
    'gpu_mem_total': 0,
    'gpu_freq': [],
    'ram_used': [],
    'ram_total': 0,
    'num_cores': 0,
    'net_download': [],
    'net_upload': []
}
MAX_POINTS = 60

# Track previous energy reading for power calculation
previous_energy = None
previous_time = None

# Track previous network bytes for speed calculation
previous_net_bytes = None
previous_net_time = None

def get_gpu_stats():
    """Get NVIDIA GPU stats"""
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=temperature.gpu,power.draw,utilization.gpu,utilization.memory,memory.used,memory.total,clocks.current.graphics',
             '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=2
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split(',')
            return {
                'temp': float(parts[0].strip()),
                'power': float(parts[1].strip()),
                'util': float(parts[2].strip()),
                'mem_util': float(parts[3].strip()),
                'mem_used': float(parts[4].strip()),
                'mem_total': float(parts[5].strip()),
                'freq': float(parts[6].strip())  # Keep in MHz
            }
    except Exception as e:
        print(f"GPU stats error: {e}")
    return None

def get_cpu_temp():
    """Get CPU temperature from sensors"""
    try:
        result = subprocess.run(['sensors'], capture_output=True, text=True, timeout=2)
        if result.returncode == 0:
            # Look for Tctl or Tdie temperature
            match = re.search(r'(Tctl|Tdie|Package id 0):\s+\+?([\d.]+)°C', result.stdout)
            if match:
                return float(match.group(2))
    except Exception as e:
        print(f"CPU temp error: {e}")
    return None

def get_cpu_fan():
    """Get CPU fan speed"""
    try:
        result = subprocess.run(['sensors'], capture_output=True, text=True, timeout=2)
        if result.returncode == 0:
            match = re.search(r'cpu_fan:\s+(\d+)\s+RPM', result.stdout)
            if match:
                return int(match.group(1))
    except Exception as e:
        print(f"CPU fan error: {e}")
    return None

def get_gpu_fan():
    """Get GPU fan speed"""
    try:
        result = subprocess.run(['sensors'], capture_output=True, text=True, timeout=2)
        if result.returncode == 0:
            match = re.search(r'gpu_fan:\s+(\d+)\s+RPM', result.stdout)
            if match:
                return int(match.group(1))
    except Exception as e:
        print(f"GPU fan error: {e}")
    return None

def get_cpu_usage():
    """Get overall CPU usage percentage"""
    try:
        result = subprocess.run(['top', '-bn1'], capture_output=True, text=True, timeout=2)
        if result.returncode == 0:
            match = re.search(r'%Cpu\(s\):\s+([\d.]+)\s+us', result.stdout)
            if match:
                return float(match.group(1))
    except Exception as e:
        print(f"CPU usage error: {e}")
    return None

def get_cpu_cores():
    """Get per-core CPU usage percentages"""
    try:
        result = subprocess.run(['mpstat', '-P', 'ALL', '1', '1'], capture_output=True, text=True, timeout=3)
        if result.returncode == 0:
            lines = result.stdout.split('\n')
            core_usage = []
            for line in lines:
                # Look for "Average:" lines with numeric CPU IDs
                if line.strip().startswith('Average:'):
                    parts = line.split()
                    # Check if second column is a number (CPU ID), not "all"
                    if len(parts) >= 12 and parts[1].isdigit():
                        try:
                            # The idle percentage is the last column
                            idle = float(parts[-1])
                            usage = 100.0 - idle
                            core_usage.append(round(usage, 2))
                        except (ValueError, IndexError):
                            continue
            return core_usage if core_usage else None
    except Exception as e:
        print(f"CPU cores error: {e}")
    return None

def get_cpu_freq():
    """Get CPU frequency in MHz"""
    try:
        with open('/proc/cpuinfo', 'r') as f:
            for line in f:
                if 'cpu MHz' in line:
                    freq_mhz = float(line.split(':')[1].strip())
                    return freq_mhz  # Return in MHz
    except Exception as e:
        print(f"CPU freq error: {e}")
    return None

def get_cpu_power():
    """Get CPU power draw from Intel RAPL"""
    global previous_energy, previous_time
    try:
        # Read energy in microjoules
        with open('/sys/class/powercap/intel-rapl:0/energy_uj', 'r') as f:
            current_energy = int(f.read().strip())
        
        current_time = time.time()
        
        if previous_energy is not None and previous_time is not None:
            # Calculate power: (energy_diff / time_diff) = watts
            energy_diff = current_energy - previous_energy
            time_diff = current_time - previous_time
            
            # Handle counter wrap-around
            if energy_diff < 0:
                with open('/sys/class/powercap/intel-rapl:0/max_energy_range_uj', 'r') as f:
                    max_range = int(f.read().strip())
                energy_diff += max_range
            
            # Convert microjoules to watts (1 watt = 1 joule/second = 1,000,000 microjoules/second)
            power_watts = (energy_diff / 1000000.0) / time_diff
            
            previous_energy = current_energy
            previous_time = current_time
            return power_watts
        else:
            # First reading, just store values
            previous_energy = current_energy
            previous_time = current_time
            return 0.0
    except Exception as e:
        print(f"CPU power error: {e}")
        return None

def get_ram_usage():
    """Get RAM usage in GB"""
    try:
        result = subprocess.run(['free', '-b'], capture_output=True, text=True, timeout=2)
        if result.returncode == 0:
            lines = result.stdout.split('\n')
            mem_line = lines[1].split()
            total = int(mem_line[1]) / (1024**3)  # Convert to GB
            used = int(mem_line[2]) / (1024**3)
            return {'used': used, 'total': total}
    except Exception as e:
        print(f"RAM usage error: {e}")
    return None

def get_network_speed():
    """Get network upload/download speed in Mbps"""
    global previous_net_bytes, previous_net_time
    try:
        current_time = time.time()
        total_rx = 0
        total_tx = 0
        
        # Read all network interfaces from /proc/net/dev
        with open('/proc/net/dev', 'r') as f:
            lines = f.readlines()[2:]  # Skip header lines
            for line in lines:
                if ':' in line:
                    parts = line.split(':')
                    iface = parts[0].strip()
                    # Skip loopback
                    if iface == 'lo':
                        continue
                    stats = parts[1].split()
                    total_rx += int(stats[0])  # Received bytes
                    total_tx += int(stats[8])  # Transmitted bytes
        
        if previous_net_bytes is not None and previous_net_time is not None:
            time_diff = current_time - previous_net_time
            rx_diff = total_rx - previous_net_bytes['rx']
            tx_diff = total_tx - previous_net_bytes['tx']
            
            # Convert to Mbps (bytes/sec * 8 / 1000000)
            download_speed = (rx_diff / time_diff) * 8 / 1000000
            upload_speed = (tx_diff / time_diff) * 8 / 1000000
            
            previous_net_bytes = {'rx': total_rx, 'tx': total_tx}
            previous_net_time = current_time
            return {'download': download_speed, 'upload': upload_speed}
        else:
            # First reading, just store values
            previous_net_bytes = {'rx': total_rx, 'tx': total_tx}
            previous_net_time = current_time
            return {'download': 0.0, 'upload': 0.0}
    except Exception as e:
        print(f"Network speed error: {e}")
        return None

def collect_data():
    """Continuously collect system metrics"""
    while True:
        try:
            timestamp = time.strftime('%H:%M:%S')
            
            # Get all stats
            gpu = get_gpu_stats()
            cpu_temp = get_cpu_temp()
            cpu_fan = get_cpu_fan()
            gpu_fan = get_gpu_fan()
            cpu_usage = get_cpu_usage()
            cpu_cores = get_cpu_cores()
            cpu_freq = get_cpu_freq()
            cpu_power = get_cpu_power()
            ram = get_ram_usage()
            net = get_network_speed()
            
            # Update history
            data_history['timestamps'].append(timestamp)
            data_history['cpu_temp'].append(cpu_temp if cpu_temp else 0)
            data_history['cpu_usage'].append(cpu_usage if cpu_usage else 0)
            data_history['cpu_cores'].append(cpu_cores if cpu_cores else [0] * data_history['num_cores'])
            data_history['cpu_freq'].append(cpu_freq if cpu_freq else 0)
            data_history['cpu_fan'].append(cpu_fan if cpu_fan else 0)
            data_history['gpu_fan'].append(gpu_fan if gpu_fan else 0)
            data_history['cpu_power'].append(cpu_power if cpu_power else 0)
            
            # Set number of cores on first successful read
            if cpu_cores and data_history['num_cores'] == 0:
                data_history['num_cores'] = len(cpu_cores)
            
            if gpu:
                data_history['gpu_temp'].append(gpu['temp'])
                data_history['gpu_power'].append(gpu['power'])
                data_history['gpu_util'].append(gpu['util'])
                data_history['gpu_mem_util'].append(gpu['mem_util'])
                data_history['gpu_mem_used'].append(gpu['mem_used'] / 1024)  # Convert MB to GB
                data_history['gpu_mem_total'] = gpu['mem_total'] / 1024  # Convert MB to GB
                data_history['gpu_freq'].append(gpu['freq'])
            else:
                data_history['gpu_temp'].append(0)
                data_history['gpu_power'].append(0)
                data_history['gpu_util'].append(0)
                data_history['gpu_mem_util'].append(0)
                data_history['gpu_mem_used'].append(0)
                data_history['gpu_freq'].append(0)
            
            if ram:
                data_history['ram_used'].append(ram['used'])
                data_history['ram_total'] = ram['total']
            else:
                data_history['ram_used'].append(0)
            
            if net:
                data_history['net_download'].append(net['download'])
                data_history['net_upload'].append(net['upload'])
            else:
                data_history['net_download'].append(0)
                data_history['net_upload'].append(0)
            
            # Keep only last MAX_POINTS
            for key in data_history:
                if isinstance(data_history[key], list) and len(data_history[key]) > MAX_POINTS:
                    data_history[key] = data_history[key][-MAX_POINTS:]
            
            time.sleep(1)
        except Exception as e:
            print(f"Collection error: {e}")
            time.sleep(1)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/data')
def get_data():
    return jsonify(data_history)

if __name__ == '__main__':
    # Start data collection in background thread
    collector_thread = threading.Thread(target=collect_data, daemon=True)
    collector_thread.start()
    
    # Start Flask server
    print("Starting monitor at http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=False)
