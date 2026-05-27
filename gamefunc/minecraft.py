import subprocess
from mcrcon import MCRcon
import os
import asyncio
import shlex

class MinecraftServer:
    def __init__(self, ctx):
        self.ctx = ctx
        # Define RCON settings for each server type
        self.rcon_settings = {
            'vanilla': {'host': "localhost", 'port': 25575, 'password': "WR>**gd123"},
            'modded': {'host': "localhost", 'port': 25575, 'password': "password123"}
        }

    async def start_server(self, server_type):
        try:
            if server_type == 'vanilla':
                minecraft_dir = '/home/trevor/Documents/Vanilla_Server'  # Update with actual path
                full_command = f'kitty --hold -d {minecraft_dir} -e bash -c "./newrun.sh"'
            elif server_type == 'modded':
                minecraft_dir = '/home/trevor/Documents/AlexServer'  # Update with actual path
                full_command = f'kitty --hold -d {minecraft_dir} -e bash -c "./newrun.sh"'
            else:
                await self.ctx.send("Invalid server type. Please use 'vanilla' or 'modded'.")
                return

            # Execute the command properly
            subprocess.Popen(shlex.split(full_command))

            await self.ctx.send(f"{server_type.capitalize()} Minecraft server started in a new Kitty terminal window.")

        except Exception as e:
            await self.ctx.send(f"Error starting {server_type} server: {str(e)}")


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