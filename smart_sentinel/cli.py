"""
Command Line Interface for Smart Sentinel Downloader (sentinel-dl).
"""

import logging
import sys
from pathlib import Path
from typing import List, Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from smart_sentinel import __version__
from smart_sentinel.auth import AuthenticationManager, CDSEAuthError
from smart_sentinel.client import CDSEClient, CDSEClientError
from smart_sentinel.config import DEFAULT_DOWNLOAD_DIR, DEFAULT_WORKERS
from smart_sentinel.downloader import Downloader

# Setup rich console
console = Console()

# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("smart_sentinel")


@click.group(context_settings=dict(help_option_names=["-h", "--help"]))
@click.version_option(__version__, "-v", "--version", prog_name="sentinel-dl")
@click.option("--debug", is_flag=True, help="Enable verbose debug logging.")
def main(debug: bool):
    """
    \b
     _____                      _      _____            _   _            _
    /  ___|                    | |    /  ___|          | | (_)          | |
    \\ `--. _ __ ___   __ _ _ __| |_   \\ `--.  ___ _ __ | |_ _ _ __   ___| |
     `--. \\ '_ ` _ \\ / _` | '__| __|   `--. \\/ _ \\ '_ \\| __| | '_ \\ / _ \\ |
    /\\__/ / | | | | | (_| | |  | |_   /\\__/ /  __/ | | | |_| | | | |  __/ |
    \\____/|_| |_| |_|\\__,_|_|   \\__|  \\____/ \\___|_| |_|\\__|_|_| |_|\\___|_|

    Fast, selective, and robust Sentinel-1 & Sentinel-2 downloader for CDSE.
    """
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)


@main.command()
def auth():
    """Verify CDSE credentials and test connectivity."""
    console.print("\n[bold cyan]Checking CDSE Authentication & Connectivity...[/bold cyan]")
    auth_mgr = AuthenticationManager()

    if not auth_mgr.username or not auth_mgr.password:
        console.print(
            "[bold red]✗ Credentials missing![/bold red]\n"
            "Please create a [bold].env[/bold] file or set environment variables:\n"
            "  SENTINEL_USER=your_email@example.com\n"
            "  SENTINEL_PASS=your_password\n"
        )
        sys.exit(1)

    try:
        token = auth_mgr.get_token(force_refresh=True)
        console.print("[bold green]✓ Successfully authenticated with CDSE![/bold green]")
        console.print(f"  User: [cyan]{auth_mgr.username}[/cyan]")
        console.print(f"  Token Preview: [dim]{token[:20]}...{token[-10:]}[/dim]\n")
    except CDSEAuthError as e:
        console.print(f"[bold red]✗ Authentication Failed:[/bold red] {e}\n")
        sys.exit(1)


@main.command()
@click.option(
    "--mission",
    "-m",
    type=click.Choice(["sentinel2", "sentinel1", "S2", "S1"], case_sensitive=False),
    default="sentinel2",
    help="Satellite mission to search for (default: sentinel2)",
)
@click.option(
    "--bbox",
    nargs=4,
    type=float,
    metavar="MIN_LON MIN_LAT MAX_LON MAX_LAT",
    help="Spatial bounding box coordinates.",
)
@click.option("--start", "-s", type=str, help="Start date (YYYY-MM-DD).")
@click.option("--end", "-e", type=str, help="End date (YYYY-MM-DD).")
@click.option("--max-cloud", "-c", type=float, default=None, help="Max cloud cover percentage (0-100).")
@click.option("--limit", "-n", type=int, default=10, help="Maximum number of results to display.")
@click.option("--download", "-d", is_flag=True, help="Immediately download matched products.")
@click.option("--bands", "-b", type=str, default="rgb", help="Band preset or list (e.g., rgb, ndvi, B04,B08).")
@click.option(
    "--export",
    "-x",
    type=click.Path(),
    default=None,
    help="Export search results to GeoJSON or CSV file (e.g. results.geojson, results.csv).",
)
@click.option("--output-dir", "-o", type=click.Path(), default=str(DEFAULT_DOWNLOAD_DIR), help="Output folder.")
def search(
    mission: str,
    bbox: Optional[tuple],
    start: Optional[str],
    end: Optional[str],
    max_cloud: Optional[float],
    limit: int,
    download: bool,
    bands: str,
    export: Optional[str],
    output_dir: str,
):
    """
    Search CDSE catalog for Sentinel products by area, date, and cloud cover.
    """
    client = CDSEClient()
    bbox_list = list(bbox) if bbox else None

    console.print(f"[bold cyan]Searching CDSE catalog for {mission.upper()} products...[/bold cyan]")
    try:
        products = client.search(
            collection=mission,
            bbox=bbox_list,
            start_date=start,
            end_date=end,
            max_cloud_cover=max_cloud,
            limit=limit,
        )
    except Exception as exc:
        console.print(f"[bold red]Search failed:[/bold red] {exc}")
        sys.exit(1)

    if not products:
        console.print("[yellow]No matching products found for the specified criteria.[/yellow]")
        return

    table = Table(title=f"Search Results ({len(products)} found)", show_lines=True)
    table.add_column("Index", justify="center", style="dim")
    table.add_column("UUID", style="cyan")
    table.add_column("Product Name", style="bold white")
    table.add_column("Date", style="green")
    table.add_column("Cloud %", justify="right", style="yellow")
    table.add_column("Size", justify="right", style="magenta")

    for idx, prod in enumerate(products, 1):
        cloud_str = f"{prod.cloud_cover:.1f}%" if prod.cloud_cover is not None else "N/A"
        size_str = f"{prod.size_mb:.1f} MB" if prod.content_length > 0 else "N/A"
        table.add_row(
            str(idx),
            prod.id[:8] + "...",
            prod.name[:45] + ("..." if len(prod.name) > 45 else ""),
            (prod.publication_date or "")[:19],
            cloud_str,
            size_str,
        )

    console.print(table)

    if export:
        from smart_sentinel.export import export_search_results
        saved_export = export_search_results(products, Path(export))
        console.print(f"\n[bold green]✓ Exported {len(products)} search results to:[/bold green] [cyan]{saved_export}[/cyan]")

    if download:
        console.print(f"\n[bold green]Triggering selective download for {len(products)} product(s)...[/bold green]")
        downloader = Downloader(client=client, download_dir=Path(output_dir))
        downloader.download_batch(
            [p.id for p in products],
            download_type="selective",
            bands=bands,
            output_dir=Path(output_dir),
        )


@main.command()
@click.argument("product_ids", nargs=-1)
@click.option("--file", "-f", "ids_file", type=click.Path(exists=True), help="Text file containing product IDs/names.")
@click.option(
    "--type",
    "-t",
    "download_type",
    type=click.Choice(["selective", "full"], case_sensitive=False),
    default="selective",
    help="Download type: 'selective' (specific bands) or 'full' (complete ZIP).",
)
@click.option(
    "--bands",
    "-b",
    type=str,
    default=None,
    help="Band preset (rgb, tci, ndvi, vnir, all) or comma-separated bands (e.g. B04,B08,SCL).",
)
@click.option(
    "--workers",
    "-w",
    type=int,
    default=DEFAULT_WORKERS,
    help=f"Concurrent download worker threads (default: {DEFAULT_WORKERS}).",
)
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(),
    default=str(DEFAULT_DOWNLOAD_DIR),
    help="Target directory for downloaded data.",
)
@click.option(
    "--composite",
    "-c",
    type=click.Choice(["rgb", "false-color", "swir"], case_sensitive=False),
    default=None,
    help="Automatically generate a 3-band GeoTIFF composite (rgb, false-color, swir).",
)
@click.option("--no-checksum", is_flag=True, help="Disable cryptographic hash verification.")
def download(
    product_ids: tuple,
    ids_file: Optional[str],
    download_type: str,
    bands: Optional[str],
    composite: Optional[str],
    workers: int,
    output_dir: str,
    no_checksum: bool,
):
    """
    Download Sentinel products as full ZIPs or selective bands.
    """
    all_ids: List[str] = list(product_ids)

    if ids_file:
        with open(ids_file, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    all_ids.append(stripped)

    if not all_ids:
        console.print("[bold red]Error:[/bold red] No product IDs provided. Pass them as arguments or via --file.")
        sys.exit(1)

    console.print(
        Panel(
            f"[bold green]Starting Sentinel Downloader[/bold green]\n"
            f"Mode: [cyan]{download_type.upper()}[/cyan] | "
            f"Bands: [cyan]{bands or 'default'}[/cyan] | "
            f"Workers: [cyan]{workers}[/cyan] | "
            f"Products: [cyan]{len(all_ids)}[/cyan]\n"
            f"Destination: [dim]{output_dir}[/dim]",
            border_style="green",
        )
    )

    client = CDSEClient()
    downloader = Downloader(
        client=client,
        download_dir=Path(output_dir),
        workers=workers,
    )

    results = downloader.download_batch(
        all_ids,
        download_type=download_type,
        bands=bands,
        output_dir=Path(output_dir),
        verify_checksum=not no_checksum,
        composite=composite,
    )

    success_count = sum(1 for r in results if r.status == "SUCCESS")
    failed_count = sum(1 for r in results if r.status != "SUCCESS")

    console.print("\n[bold]Download Summary:[/bold]")
    console.print(f"  [bold green]✓ Successful:[/bold green] {success_count}")
    if failed_count > 0:
        console.print(f"  [bold red]✗ Failed:[/bold red] {failed_count}")
        for r in results:
            if r.status != "SUCCESS":
                console.print(f"    - {r.product_id}: {r.error_message}")


@main.command()
@click.argument("product_id")
def info(product_id: str):
    """
    Inspect product metadata and view internal band assets.
    """
    client = CDSEClient()
    console.print(f"[bold cyan]Fetching metadata for {product_id}...[/bold cyan]")

    try:
        product = client.get_product(product_id)
    except CDSEClientError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)

    console.print(
        Panel(
            f"[bold white]{product.name}[/bold white]\n"
            f"UUID: [cyan]{product.id}[/cyan]\n"
            f"Mission: [green]{product.mission.upper()}[/green]\n"
            f"Size: [magenta]{product.size_mb:.2f} MB ({product.size_gb:.2f} GB)[/magenta]\n"
            f"Publication Date: {product.publication_date or 'N/A'}\n"
            f"Checksum ({product.checksum_algorithm}): [dim]{product.checksum or 'N/A'}[/dim]",
            title="Product Overview",
            border_style="cyan",
        )
    )

    console.print("[dim]Fetching internal asset nodes...[/dim]")
    files = client.list_product_files(product.id)

    table = Table(title=f"Internal Files ({len(files)} items)", show_lines=False)
    table.add_column("Filename", style="bold")
    table.add_column("Size", justify="right", style="magenta")
    table.add_column("Checksum", style="dim")

    for f in files:
        size_str = f"{f.size_mb:.2f} MB" if f.content_length > 0 else "< 1 MB"
        chk = f.checksum[:10] + "..." if f.checksum else "N/A"
        table.add_row(f.name, size_str, chk)

    console.print(table)


if __name__ == "__main__":
    main()
