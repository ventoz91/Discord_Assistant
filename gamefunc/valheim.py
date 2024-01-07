import subprocess

class ValheimServer:
    def __init__(self):
        # Server configuration
        self.server_executable = 'I:\\SteamLibrary\\steamapps\\common\\Valheim dedicated server\\valheim_server.exe'
        self.server_name = "MyValheimServer"
        self.world_name = "catss"
        self.server_password = "kbt123"

    def start_server(self):
        command = f'start cmd.exe /k "{self.server_executable}" -name "{self.server_name}" -world "{self.world_name}" -password "{self.server_password}"'
        subprocess.Popen(command, shell=True)
        return f"Valheim server '{self.server_name}' started."
