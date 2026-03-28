import subprocess
import sys
import os
import time
import signal
import re
import socket
import json
import pathlib
from datetime import datetime

# Import rich directly - assuming it's always available in the correct environment
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout
from rich.status import Status
from rich.text import Text
from rich.columns import Columns
from rich import box

# Configuration
PORT_DJANGO = 8000
PORT_FLASK = 5001
VENV_PYTHON = os.path.join(".venv", "Scripts", "python.exe")
REQUIREMENTS = "requirements.txt"
BASE_DIR = pathlib.Path(__file__).resolve().parent
SYNC_CACHE_PATH = BASE_DIR / "drive_cache.json"

# Self-restart logic to ensure we're in the .venv
def ensure_venv():
    """Restarts the script using the .venv python if not already running from there."""
    current_python = sys.executable
    venv_python = str(BASE_DIR / VENV_PYTHON)
    
    # Check if we are already using the venv python
    if current_python.lower() != venv_python.lower():
        if os.path.exists(venv_python):
            print(f"[*] Re-launching with virtual environment: {VENV_PYTHON}")
            try:
                os.execv(venv_python, [venv_python] + sys.argv)
            except Exception as e:
                print(f"[!] Critical: Failed to restart with .venv python: {e}")
                sys.exit(1)
        else:
            print(f"[!] Warning: Virtual environment not found at {VENV_PYTHON}")

ensure_venv()

class PAIKSLauncher:
    def __init__(self):
        self.console = Console()
        self.processes = []
        self.start_time = datetime.now()
        self.stats = {
            "docs_total": 0,
            "last_sync": "Never",
            "flask_status": "[red]Offline[/red]",
            "django_status": "[red]Offline[/red]",
        }

    def get_project_stats(self):
        """Load real stats from the drive cache."""
        if SYNC_CACHE_PATH.exists():
            try:
                data = json.loads(SYNC_CACHE_PATH.read_text(encoding="utf-8"))
                self.stats["docs_total"] = data.get("total", 0)
                synced_at = data.get("synced_at", "Unknown")
                if synced_at != "Unknown":
                    dt = datetime.fromisoformat(synced_at.replace("Z", "+00:00"))
                    self.stats["last_sync"] = dt.strftime("%Y-%m-%d %H:%M")
            except:
                pass

    def check_port(self, port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('127.0.0.1', port)) == 0

    def kill_process_on_port(self, port):
        if not self.check_port(port):
            return True
        try:
            output = subprocess.check_output(f'netstat -ano | findstr :{port}', shell=True).decode()
            pids = set(re.findall(r'\s+(\d+)\s*$', output, re.MULTILINE))
            for pid in pids:
                if pid == '0': continue
                subprocess.run(f'taskkill /F /PID {pid} /T', shell=True, capture_output=True)
            time.sleep(1)
            return not self.check_port(port)
        except:
            return False

    def ensure_dependencies(self):
        with self.console.status("[bold blue]Verifying dependencies...", spinner="dots"):
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "-r", REQUIREMENTS])
            except Exception as e:
                self.console.print(f"[bold red]Error updating dependencies: {e}[/bold red]")

    def make_dashboard(self):
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main", ratio=1),
            Layout(name="footer", size=3)
        )
        
        # Header
        header_text = Text("PAIKS - Google Drive AI Assistant", style="bold white on blue", justify="center")
        layout["header"].update(Panel(header_text, box=box.HORIZONTALS))

        # Main Content (Stats & Status)
        main_table = Table.grid(expand=True)
        main_table.add_column(ratio=1)
        main_table.add_column(ratio=1)

        # Status Table
        status_table = Table(box=box.ROUNDED, expand=True, border_style="bright_blue")
        status_table.add_column("Service", style="cyan")
        status_table.add_column("Status", justify="center")
        status_table.add_column("Endpoint", style="green")
        
        status_table.add_row("Flask Search API", self.stats["flask_status"], f"http://127.0.0.1:{PORT_FLASK}")
        status_table.add_row("Django Frontend", self.stats["django_status"], f"http://127.0.0.1:{PORT_DJANGO}")

        # Stats Panel
        uptime = str(datetime.now() - self.start_time).split(".")[0]
        stats_text = Text.assemble(
            ("Project Metrics\n", "bold magenta"),
            (f"Total Documents: ", "white"), (f"{self.stats['docs_total']}\n", "bold yellow"),
            (f"Last Sync:      ", "white"), (f"{self.stats['last_sync']}\n", "bold yellow"),
            (f"Uptime:         ", "white"), (f"{uptime}", "bold yellow")
        )
        stats_panel = Panel(stats_text, title="Database & Stats", border_style="bright_magenta", box=box.ROUNDED, expand=True)

        main_table.add_row(status_table, stats_panel)
        layout["main"].update(main_table)

        # Footer
        footer_text = Text("Press CTRL+C to safely shutdown all services", style="italic dim", justify="center")
        layout["footer"].update(Panel(footer_text, box=box.HORIZONTALS))

        return layout

    def start(self):
        try:
            self.ensure_dependencies()
            self.get_project_stats()

            with self.console.status("[bold blue]Cleaning environment...", spinner="dots"):
                self.kill_process_on_port(PORT_DJANGO)
                self.kill_process_on_port(PORT_FLASK)

            # Start Flask
            flask_proc = subprocess.Popen(
                [sys.executable, "flask_api.py"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            self.processes.append(flask_proc)
            time.sleep(2)
            if flask_proc.poll() is None:
                self.stats["flask_status"] = "[bold green]Online[/bold green]"

            # Start Django
            django_proc = subprocess.Popen(
                [sys.executable, "manage.py", "runserver", str(PORT_DJANGO)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            self.processes.append(django_proc)
            time.sleep(1)
            if django_proc.poll() is None:
                self.stats["django_status"] = "[bold green]Online[/bold green]"

            with Live(self.make_dashboard(), refresh_per_second=1, console=self.console) as live:
                while True:
                    if flask_proc.poll() is not None:
                        self.stats["flask_status"] = "[bold red]Crashed[/bold red]"
                    if django_proc.poll() is not None:
                        self.stats["django_status"] = "[bold red]Crashed[/bold red]"
                    
                    self.get_project_stats() # Refresh stats
                    live.update(self.make_dashboard())
                    time.sleep(1)

        except KeyboardInterrupt:
            self.console.print("\n[bold yellow]Shutting down services safely...[/bold yellow]")
        except Exception as e:
            self.console.print(f"[bold red]Critical Error: {e}[/bold red]")
        finally:
            for p in self.processes:
                try:
                    subprocess.run(f'taskkill /F /PID {p.pid} /T', shell=True, capture_output=True)
                except:
                    pass
            self.console.print("[bold green]All services stopped. Goodbye![/bold green]")

if __name__ == "__main__":
    launcher = PAIKSLauncher()
    launcher.start()
