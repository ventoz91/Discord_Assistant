import subprocess 
from mcrcon import MCRcon
import os
import asyncio

class MinecraftServer:
    def __init__(self, ctx):
        self.ctx = ctx
        # Define RCON settings for each server type
        self.rcon_settings = {
            'vanilla': {'host': "localhost", 'port': 25575, 'password': "WR>**gd123"},
            'modded': {'host': "localhost", 'port': 25576, 'password': "WR>**gd123"}
        }

    async def start_server(self, server_type):
        try:
            if server_type == 'vanilla':
                minecraft_dir = 'C:\\Users\\t_klo\\Documents\\Scripts\\OpenAI - Refactor Project\\Vanilla_Server'
                jar_file = 'fabric-server-mc.1.20.1-loader.0.14.22-launcher.0.11.2.jar'  # Update this to your server JAR file name
            elif server_type == 'modded':
                minecraft_dir = 'C:\\Users\\t_klo\\Desktop\\All+of+Fabric+7-Server-0.5.2'
                jar_file = 'serverstarter-2.4.0.jar'  # Update this to your modded server JAR file name
            else:
                await self.ctx.send("Invalid server type. Please use 'vanilla' or 'modded'.")
                return

            java_command = f'java -Xmx6G -jar {jar_file} nogui'
            full_command = f'cmd.exe /c "cd /d {minecraft_dir} && start cmd.exe /k {java_command}"'
            modded_javacommand = f'java -jar {jar_file}'
            full_modded = f'cmd.exe /c "cd /d {minecraft_dir} && start cmd.exe /k {modded_javacommand}"'
            # Change the working directory and execute the command
            os.chdir(minecraft_dir)
            if server_type == 'vanilla':
                subprocess.Popen(full_command, shell=True)
            elif server_type == 'modded':
                subprocess.Popen(full_modded, shell=True)
            else:
                await self.ctx.send("error")
                return
            
            await self.ctx.send(f"{server_type.capitalize()} Minecraft server started in a new window.")

        except Exception as e:
            await self.ctx.send(f"An error occurred: {e}")

    async def stop_server(self, server_type):
        try:
            if server_type not in self.rcon_settings:
                await self.ctx.send("Invalid server type. Please use 'vanilla' or 'modded'.")
                return

            # Get the RCON settings for the specified server type
            rcon_info = self.rcon_settings[server_type]

            # Send RCON command to stop the server
            with MCRcon(rcon_info['host'], rcon_info['password'], rcon_info['port']) as mcr:
                resp = mcr.command("stop")
                await self.ctx.send(f"Response from {server_type} server: {resp}")

        except Exception as e:
            await self.ctx.send(f"An error occurred while stopping the server: {e}")

    async def restart_server(self, server_type):
        try:
            if server_type not in self.rcon_settings:
                await self.ctx.send("Invalid server type. Please use 'vanilla' or 'modded'.")
                return

            # Step 1: Stop the server
            await self.stop_server(server_type)

            # Wait for a few seconds to ensure the server stops
            await asyncio.sleep(10)  # You can adjust the delay as needed

            # Step 2: Start the server
            await self.start_server(server_type)

        except Exception as e:
            await self.ctx.send(f"An error occurred while restarting the server: {e}")

    async def list_players(self, server_type):
        try:
            if server_type not in self.rcon_settings:
                await self.ctx.send("Invalid server type. Please use 'vanilla' or 'modded'.")
                return

            rcon_info = self.rcon_settings[server_type]

            with MCRcon(rcon_info['host'], rcon_info['password'], rcon_info['port']) as mcr:
                resp = mcr.command("list")
                await self.ctx.send(f"Current players on {server_type} server: {resp}")

        except Exception as e:
            await self.ctx.send(f"An error occurred while retrieving player list: {e}")


#######FutureUSE#######
            
#import paramiko

# def run_ssh_command_with_paramiko(command, hostname, username, password):
#     client = paramiko.SSHClient()
#     client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
#     client.connect(hostname, username=username, password=password)

#     stdin, stdout, stderr = client.exec_command(command)
#     output = stdout.read()
#     client.close()
#     return output

# # Construct your full_command as you did before
# full_command = f'java -Xmx6G -jar {jar_file} nogui'

# # Pass this full_command to the function along with SSH details
# output = run_ssh_command_with_paramiko(full_command, 'raspberry.lan', 'username', 'password')
# print(output)