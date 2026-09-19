import typer
from rich.console import Console

app = typer.Typer(help="Argus - AI-Powered Smart Security System")
console = Console()

@app.command()
def start():
    """Start the Argus core system."""
    console.print("[bold green]Starting Argus...[/bold green]")
    console.print("[yellow]Initialization sequence triggered. Core pipeline loading...[/yellow]")
    # TODO: Import and start main pipeline

@app.command()
def dashboard():
    """Launch the Argus Streamlit dashboard."""
    console.print("[bold blue]Launching Argus Dashboard...[/bold blue]")
    import subprocess
    subprocess.run(["streamlit", "run", "argus/dashboard/app.py"])

if __name__ == "__main__":
    app()
