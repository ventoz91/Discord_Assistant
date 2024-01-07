import subprocess
import os
import psutil

class ValheimServer:
    def __init__(self):
        # Server configuration
        self.server_name = "MyValheimServer"
        self.world_name = "catss"
        self.server_password = "kbt123"
        self.steam_directory = 'I:\\SteamLibrary'

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
