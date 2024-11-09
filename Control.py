# Flask-based Web Application for Video Management
from flask import Flask, request, redirect, render_template_string, session, jsonify
import subprocess
import os
import signal
import logging
import re

# Optional AI Libraries (currently commented out, planned to be integrated)
# import tensorflow as tf
# import tensorflow_hub as hub
# import numpy as np
# from PIL import Image
# from io import BytesIO

app = Flask(__name__)
app.secret_key = '***' 

# Detailed Logging Setup for Debugging and Monitoring
logging.basicConfig(
    filename='flask_app.log',
    filemode='a',
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG  # Set to DEBUG for detailed logging
)

# Scalable Subprocess Management for Video Streaming
subprocesses = {}
device_states = {}
device_list = []  

# 'ffmpeg' with the full path to the ffmpeg binary
FFMPEG_PATH = '/home/rf/bin/ffmpeg'

# Preloaded list of resolutions and frame rates
PRELOADED_FORMATS = [
    "ntsc: 720x486 at 30000/1001 fps (interlaced, lower field first)",
    "nt23: 720x486 at 24000/1001 fps",
    "pal: 720x576 at 25000/1000 fps (interlaced, upper field first)",
    "23ps: 1920x1080 at 24000/1001 fps",
    "24ps: 1920x1080 at 24000/1000 fps",
    "Hp25: 1920x1080 at 25000/1000 fps",
    "Hp29: 1920x1080 at 30000/1001 fps",
    "Hp30: 1920x1080 at 30000/1000 fps",
    "Hp50: 1920x1080 at 50000/1000 fps",
    "Hp59: 1920x1080 at 60000/1001 fps",
    "Hp60: 1920x1080 at 60000/1000 fps",
    "Hi50: 1920x1080 at 25000/1000 fps (interlaced, upper field first)",
    "Hi59: 1920x1080 at 30000/1001 fps (interlaced, upper field first)",
    "Hi60: 1920x1080 at 30000/1000 fps (interlaced, upper field first)",
    "hp50: 1280x720 at 50000/1000 fps",
    "hp59: 1280x720 at 60000/1001 fps",
    "hp60: 1280x720 at 60000/1000 fps"
]






# Following portions of the code is a draft

'''
# Load pre-trained model from TensorFlow Hub 
model_url = 'https://tfhub.dev/google/edsr/1'
model = hub.KerasLayer(model_url)

def preprocess_frame(frame):
    """ Preprocess image frame for model input """
    img = Image.open(BytesIO(frame))
    img = img.convert('RGB')
    img = img.resize((224, 224))  # To resize to the model input size
    img_array = np.array(img) / 255.0
    return np.expand_dims(img_array, axis=0)

def postprocess_frame(frame):
    """ Postprocess model output to image """
    img_array = np.squeeze(frame)
    img_array = (img_array * 255.0).astype(np.uint8)
    img = Image.fromarray(img_array)
    buf = BytesIO()
    img.save(buf, format='JPEG')
    return buf.getvalue()

def enhance_frame(frame):
    """ Enhance the quality of a video frame """
    preprocessed_frame = preprocess_frame(frame)
    enhanced_frame = model(preprocessed_frame)
    return postprocess_frame(enhanced_frame)
'''








# Function to display logs
@app.route('/logs_data')
def logs_data():
    try:
        log_file_path = '/home/rf/Desktop/flask_app.log'  
        with open(log_file_path, 'r') as file:
            logs = file.readlines()
    except Exception as e:
        logs = [f"Error reading log file: {str(e)}"]

    # Return logs as JSON
    return {'logs': logs}

# Function to execute the ffmpeg command to get the list of available DeckLink devices (From Blackmagic Design) installed on the server machine
def get_decklink_devices():
    try:
        logging.info("Executing ffmpeg to list DeckLink devices")
        output = subprocess.check_output(f"{FFMPEG_PATH} -sinks decklink", shell=True, stderr=subprocess.STDOUT)
        devices = []
        for line in output.decode('utf-8').split('\n'):
            if 'none' in line and '(none)' in line:
                device_name = line.split('[')[1].split(']')[0]
                devices.append(device_name)
                device_states[device_name] = 'inactive'
        logging.info(f"Found devices: {devices}")
        return devices
    except subprocess.CalledProcessError as e:
        logging.error(f"Error listing DeckLink devices: {e}")
        return []

# Function to get formats for a DeckLink device selected by a user from dropdown menu
def get_device_formats(device_name):
    try:
        logging.info(f"Executing ffmpeg to list formats for {device_name}")
        output = subprocess.check_output(f'{FFMPEG_PATH} -f decklink -list_formats 1 -i "{device_name}"', shell=True, stderr=subprocess.STDOUT)
        formats = []
        format_section = False
        for line in output.decode('utf-8').split('\n'):
            if 'format_code' in line and 'description' in line:
                format_section = True
                continue
            elif '[in' in line:
                break
            elif format_section and line.strip():
                formats.append(line.strip())
        logging.info(f"Found formats: {formats}")
        return formats
    except subprocess.CalledProcessError as e:
        logging.error(f"Error listing formats for {device_name}: {e}")
        logging.info(f"Using preloaded formats due to error: {PRELOADED_FORMATS}")
        return PRELOADED_FORMATS

# Route to parse formats for a specific device
@app.route('/get_formats/<device_name>', methods=['GET'])
def get_formats(device_name):
    formats = get_device_formats(device_name)
    return jsonify(formats)

# Function to format Resolution and Frame rate
def extract_resolution_and_frame_rate(format_string):
    match = re.search(r'(\d+x\d+) at (\d+/\d+)', format_string)
    if match:
        resolution = match.group(1)
        frame_rate = match.group(2)
        logging.debug(f"Extracted resolution: {resolution}, frame_rate: {frame_rate}")
        return resolution, frame_rate
    logging.debug(f"Failed to extract resolution and frame rate from: {format_string}")
    return None, None  # Handle the case if no match is found

# Function to execute the ffmpeg 'start' command
def start_command(device, input_url, resolution_frame_rate):
    resolution, frame_rate = extract_resolution_and_frame_rate(resolution_frame_rate)
    if not resolution or not frame_rate:
        logging.error(f"Invalid resolution or frame rate: resolution={resolution}, frame_rate={frame_rate}")
        return "Invalid resolution or frame rate.", None
    command = f'{FFMPEG_PATH} -re -i {input_url} -pix_fmt uyvy422 -s {resolution} -r {frame_rate} -f decklink "{device}"'
    try:
        logging.info(f"Starting ffmpeg with command: {command}")
        proc = subprocess.Popen(command, shell=True, preexec_fn=os.setsid)
        subprocesses[device] = proc
        update_device_states(device, 'active')
        logging.info(f"Started streaming to {device}")
        return f"Started streaming to {device}\n", command
    except Exception as e:
        logging.error(f"Error starting ffmpeg command: {e}")
        return str(e), command

# Function to execute the ffmpeg 'stop' command
def stop_command(device):
    try:
        if device in subprocesses:
            proc = subprocesses[device]
            os.killpg(os.getpgid(proc.pid), signal.SIGINT)
            proc.wait()
            del subprocesses[device]
            update_device_states(device, 'inactive')
            logging.info(f"Stopped streaming to {device}")
            return "Streaming stopped successfully."
        else:
            logging.error(f"No subprocess found for device: {device}")
            return "No active streaming session found for the device."
    except Exception as e:
        logging.error(f"Exception occurred: {str(e)}")
        return f"Exception occurred: {str(e)}"

# Function to update the state of a device
def update_device_states(device, state):
    global device_states
    device_states[device] = state
    logging.info(f"Device {device} state updated to {state}")

# Function to return device state
@app.route('/device_state/<device_name>', methods=['GET'])
def device_state(device_name):
    state = device_states.get(device_name, 'inactive')
    logging.info(f"Device state for {device_name}: {state}")
    return jsonify(state)

# Route for the login page
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == 'admin' and password == '****':  
            session['logged_in'] = True
            return redirect('/control')
        else:
            return "Invalid credentials"
    return render_template_string('''
    <html>
    <body>
        <h2>Login</h2>
        <form method="post">
            <label for="username">Username:</label>
            <input type="text" id="username" name="username"><br><br>
            <label for="password">Password:</label>
            <input type="password" id="password" name="password"><br><br>
            <input type="submit" value="Login">
        </form>
    </body>
    </html>
    ''')

# Route to handle logout
@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect('/')

# Route for the control page
@app.route('/control', methods=['GET', 'POST'])
def control():
    if not session.get('logged_in'):
        return redirect('/')

    message = ''
    command = ''
    
    # Check if the refresh button was clicked
    if request.method == 'POST' and 'refresh' in request.form:
        decklink_devices = get_decklink_devices()
    else:
        # Use cached device list if available
        decklink_devices = list(device_states.keys()) if device_states else get_decklink_devices()

    formats = PRELOADED_FORMATS

    if request.method == 'POST' and 'device' in request.form:
        device = request.form['device']
        logging.info(f"Selected device: {device}")
        formats = get_device_formats(device)
        if formats == PRELOADED_FORMATS:
            logging.info(f"Populating dropdown with preloaded formats for device: {device}")
        else:
            logging.info(f"Populating dropdown with dynamic formats for device: {device}")

    if request.method == 'POST' and 'action' in request.form:
        action = request.form['action']
        device = request.form['device']
        input_type = request.form.get('input_type')
        input_key = request.form.get('input_key')
        port_number = request.form.get('port_number')
        resolution_frame_rate = request.form.get('resolution_frame_rate')

        if action == 'start':
            if input_type and input_key and port_number and resolution_frame_rate:
                if input_type == "RTMP":
                    input_url = f"rtmp://27.131.14.34:{port_number}/live/{input_key}"
                else:
                    input_url = f"srt://27.131.14.34:{port_number}/live/stream/{input_key}"
                message, command = start_command(device, input_url, resolution_frame_rate)
            else:
                message = "Please provide all the required details to start streaming."
        elif action == 'stop':
            message = stop_command(device)

    # Add the initial device formats here
    initial_device = decklink_devices[0] if decklink_devices else ''
    if initial_device:
        formats = get_device_formats(initial_device)
    return render_template_string('''
<!doctype html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Control Page</title>
    <style>
        /* Style for video players */
        #media-players {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            justify-content: center;
        }

        video {
            border: 2px solid #333;
            border-radius: 8px;
        }
    </style>
    <script>
        async function updateFormats(deviceName) {
            const response = await fetch('/get_formats/' + deviceName);
            const formats = await response.json();
            const formatSelect = document.getElementById('resolution_frame_rate');
            formatSelect.innerHTML = '';
            formats.forEach(format => {
                const option = document.createElement('option');
                option.value = format;
                option.textContent = format;
                formatSelect.appendChild(option);
            });
        }

        async function updateActionButton(deviceName) {
            const response = await fetch('/device_state/' + deviceName);
            const state = await response.json();
            const actionButton = document.querySelector('button[name="action"]');
            if (state === 'active') {
                actionButton.textContent = 'Stop Streaming';
                actionButton.value = 'stop';
            } else {
                actionButton.textContent = 'Start Streaming';
                actionButton.value = 'start';
            }
        }

        async function fetchLogs() {
            try {
                const response = await fetch('/logs_data');
                const data = await response.json();
                const logContainer = document.getElementById('log-contents');
                logContainer.innerHTML = data.logs.map(line => `<div>${line}</div>`).join('');
            } catch (error) {
                console.error('Error fetching logs:', error);
            }
        }

        function updateVideoSources() {
            // Example stream URLs; replace these with actual stream URLs
            const streamUrls = [
                ****[To be assigned dynamically]
	            	****
	            	****
		            ****
            ];

            document.getElementById('player1').src = streamUrls[0];
            document.getElementById('player2').src = streamUrls[1];
            document.getElementById('player3').src = streamUrls[2];
            document.getElementById('player4').src = streamUrls[3];
        }

        document.addEventListener('DOMContentLoaded', () => {
            const deviceSelect = document.getElementById('device');
            deviceSelect.addEventListener('change', (event) => {
                updateFormats(event.target.value);
                updateActionButton(event.target.value);
            });

            // Automatically update formats and action button when the page loads
            const initialDevice = deviceSelect.value;
            if (initialDevice) {
                updateFormats(initialDevice);
                updateActionButton(initialDevice);
            }

            // Fetch logs every 5 seconds
            setInterval(fetchLogs, 5000);
            // Fetch logs initially
            fetchLogs();

            // Update video sources when page loads
            updateVideoSources();
        });
    </script>
</head>
<body>
    <h1>Control Page</h1>
    <form method="post">
        <p>Device:
            <select name="device" id="device">
                {% for device in devices %}
                    <option value="{{ device }}" {% if device == initial_device %}selected{% endif %}>{{ device }}</option>
                {% endfor %}
            </select>
        </p>
        <p>
            <button type="submit" name="action" value="start">Start Streaming</button>
        </p>
        <p>Resolution and Frame Rate:
            <select name="resolution_frame_rate" id="resolution_frame_rate">
                {% for format in formats %}
                    <option value="{{ format }}">{{ format }}</option>
                {% endfor %}
            </select>
        </p>
        <p>Input Type:
            <select name="input_type">
                <option value="RTMP">RTMP</option>
                <option value="SRT">SRT</option>
            </select>
        </p>
        <p>Port Number: <input type="text" name="port_number"></p>
        <p>Input Key: <input type="text" name="input_key"></p>
        <p><button type="submit" name="refresh">Refresh</button></p>
        <p><button type="button" onclick="document.getElementById('reboot-form').submit();">Reboot</button></p>
        <p><button type="button" onclick="window.location.href='/logout';">Logout</button></p>
    </form>
    <form id="reboot-form" method="post" action="/reboot" style="display:none;"></form>
    <form action="/restart" method="post" id="restart-form">
        <button type="submit">Restart Flask App</button>
    </form>
    <script>
        document.getElementById('restart-form').onsubmit = function(event) {
            event.preventDefault();
            fetch('/restart', { method: 'POST' })
                .then(response => {
                    setTimeout(function() {
                        window.location.href = '/'; 
                    }, 5000); 
                })
                .catch(error => console.error('Error:', error));
        };
    </script>
    <h2>Log File Contents</h2>
    <div id="log-contents"> 
    </div>
    <h2>Check stream</h2>
    <div id="media-players">
        <video id="player1" controls width="320" height="240"></video>
        <video id="player2" controls width="320" height="240"></video>
        <video id="player3" controls width="320" height="240"></video>
        <video id="player4" controls width="320" height="240"></video>
    </div>
    <p>{{ message }}</p>
    <p>{{ command }}</p>
</body>
</html>
''', devices=decklink_devices, formats=formats, message=message, command=command, initial_device=initial_device)


# Route to restart the flask application
@app.route('/restart', methods=['POST'])
def restart_flaskapp():
    if not session.get('logged_in'):
        return redirect('/')
    try:
        # Restart the Flask app
        result = subprocess.run(['/usr/bin/sudo', '/bin/systemctl', 'restart', 'flaskapp'], capture_output=True, text=True)
        if result.returncode == 0:
            app.logger.info("Flask app restart command executed successfully.")
            # Redirect to the login page
            return redirect('/')
        else:
            app.logger.error(f"Error: {result.stderr}")
            return f"Error: {result.stderr}"
    except Exception as e:
        app.logger.error(f"Exception: {str(e)}")
        return str(e)

# Route to reboot the server
@app.route('/reboot', methods=['POST'])
def reboot():
    if not session.get('logged_in'):
        return redirect('/')
    try:
        result = subprocess.run(['/usr/bin/sudo', '/usr/sbin/reboot'], capture_output=True, text=True)
        if result.returncode == 0:
            app.logger.info("Reboot command executed successfully.")
            return "Rebooting server..."
        else:
            app.logger.error(f"Error: {result.stderr}")
            return f"Error: {result.stderr}"
    except Exception as e:
        app.logger.error(f"Exception: {str(e)}")
        return str(e)
        
# Run the application
if __name__ == '__main__':
    logging.info("Starting the Flask application")
    app.run(host='0.0.0.0', port=1971)
    app.run(debug=True)
