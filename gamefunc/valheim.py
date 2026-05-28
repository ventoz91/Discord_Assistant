import subprocess
import os
import psutil

class ValheimServer:
    def __init__(self):
        self.server_name      = os.getenv('VALHEIM_SERVER_NAME', 'MyValheimServer')
        self.world_name       = os.getenv('VALHEIM_WORLD_NAME', 'MyWorld')
        self.server_password  = os.getenv('VALHEIM_PASSWORD', '')
        self.steam_directory  = os.getenv('VALHEIM_STEAM_DIR', '')

    def create_valheim_server_batch_file(self):
        batch_file_path = os.path.join(self.steam_directory, 'URDediServ.bat')

        if not os.path.exists(batch_file_path):
            os.makedirs(os.path.dirname(batch_file_path), exist_ok=True)

            with open(batch_file_path, "w") as filepath:
                filepath.write('@ECHO OFF\n'
                               'title "valheimserver"\n'
                               'color a\n'
                               '\n'
                               'ECHO UPDATING VALHEIM DEDICATED SERVER\n'
                               'ECHO ===================================================\n'
                               f'\ncd /D {self.steam_directory}\n'
                               'steamcmd +login anonymous +app_update 896660 validate +exit\n'
                               '\n'
                               'ECHO STARTING THE SERVER...\n'
                               'ECHO ===================================================\n'
                               f'\ncd "{os.path.join(self.steam_directory, "steamapps", "common", "Valheim dedicated server")}"\n'
                               '\n'
                               'set SteamAppId=892970\n'
                               '\n'
                               'echo "Starting server PRESS CTRL-C to exit"\n'
                               '\n'
                               f'valheim_server -nographics -batchmode -name "{self.server_name}" -port 2456 -world "{self.world_name}" -password "{self.server_password}" -crossplay')

        return batch_file_path

    def start_server(self):
        batch_file_path = self.create_valheim_server_batch_file()

        subprocess.Popen([batch_file_path], creationflags=subprocess.CREATE_NEW_CONSOLE)
        print('STANDING BY FOR SERVER UPDATE, BOOT, AND MINIMIZING THE WINDOW')
        print('======================================\n')
        # Additional logic for checking server status can be implemented here

        return f"Valheim server '{self.server_name}' starting..."
    
    def stop_server(self):
        batch_file_path = os.path.join(os.getcwd(), 'batch_files', 'server_reset.bat')

        if not os.path.exists(batch_file_path):
            os.makedirs(os.path.dirname(batch_file_path), exist_ok=True)
            
            with open(batch_file_path, "w") as filepath:
                filepath.write('@ECHO OFF\n'
                               'taskkill /F /IM valheim_server.exe\n'
                               'ECHO Valheim server stopped.')

        subprocess.Popen([batch_file_path], creationflags=subprocess.CREATE_NEW_CONSOLE)
        return "Stopping Valheim server..."
    
    def server_status(self):
        print('CHECKING THE STATUS OF THE SERVER...')
        print('========================================\n')
        server_up_down = "valheim_server.exe" in (i.name() for i in psutil.process_iter())
        print('THE SERVER IS CURRENTLY RUNNING:', server_up_down, '\n')
        if server_up_down:
            return "Valheim server is currently running!"
        else:
            return "Valheim server is not running."


class EnshroudedServer:

    def start_server(self):
        exe_path = os.getenv('ENSHROUDED_EXE', '')
        if not exe_path:
            return "Enshrouded server path not configured (set ENSHROUDED_EXE in .env)."
        subprocess.Popen([exe_path], creationflags=subprocess.CREATE_NEW_CONSOLE)
        return "Enshrouded server starting..."
    
    def stop_server(self, task_name):
        # Check if the task is running
        try:
            # This command lists the tasks and finds the task_name in the list
            subprocess.check_call(['tasklist', '/FI', f'IMAGENAME eq {task_name}'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # If the above command doesn't throw an exception, the task is running and can be killed
            subprocess.check_call(['taskkill', '/F', '/IM', task_name])
            return f"Task {task_name} has been successfully terminated."
        except subprocess.CalledProcessError:
            # The task is not running
            return f"No task named {task_name} is currently running."

    # # Replace 'enshrouded_server.exe' with the name of your server executable if different
    # stop_server('enshrouded_server.exe')
    
