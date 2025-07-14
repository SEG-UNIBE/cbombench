"""
Command Line Interface to compare different CBOM-generation tools
"""
import click
import json
import time
from adapter.github_endpoint import find_repos, get_repo_info
from adapter.cbomkit import CBOMkitClient
from adapter.deepseek import DeepSeekClient
from adapter.cdxgen import generate_cbom as generate_cdx_cbom
from cbom_analyzer import CBOMComparisonAnalyzer
from data_handler import save_cbom, delete_data as delete

# --- Initialize tool clients and analyzer ---
# These instances are created once and reused by the CLI commands.
cbomkit = CBOMkitClient()
deepseek = DeepSeekClient()
analyzer = CBOMComparisonAnalyzer()


@click.group()
def cli():
    """
    cbombench - A CLI tool for benchmarking different CBOM-generation tools.

    This tool allows finding GitHub repositories, running benchmarks on them
    with various CBOM tools, analyzing the results, and viewing reports.
    """
    pass


@cli.command()
def delete_data():
    """Delete all generated CBOM data and performance metrics."""
    delete()


@cli.command()
@click.option('--language', '-l', default='java', help='Programming language to filter by.')
@click.option('--min-size', '-s', default=1000, type=int, help='Minimum repository size in KB.')
@click.option('--max-size', '-m', default=500000, type=int, help='Maximum repository size in KB.')
@click.option('--sample-size', '-n', default=5, type=int, help='Number of repositories to return.')
def get_repos(language, min_size, max_size, sample_size):
    """
    Find random GitHub repositories that match specified criteria.

    This command uses the GitHub API to search for repositories based on language,
    size, and recent activity, then prints a random sample.
    """
    click.echo(f"Searching for {sample_size} {language} repositories with minimum size of {min_size}KB...")
    repos = find_repos(language=language, min_size=min_size, max_size=max_size, sample_size=sample_size)
    if repos:
        click.echo("\nFound repositories:")
        # Print details for each found repository.
        for full_name, clone_url, default_branch, size in repos:
            click.echo(f"- {full_name} | {clone_url} | branch: {default_branch} | size: {size}KB")
    else:
        click.echo(click.style("No repositories found matching your criteria.", fg='red'))


@cli.command()
@click.argument('kits', nargs=-1)
@click.option('--language', '-l', default='java', help='Programming language to filter by.')
@click.option('--min-size', '-s', default=1000, type=int, help='Minimum repository size in KB.')
@click.option('--max-size', '-m', default=1000000, type=int, help='Maximum repository size in KB.')
@click.option('--sample-size', '-n', default=1, type=int, help='Number of repositories to benchmark on.')
def benchmark(kits, language, min_size, max_size, sample_size):
    """
    Benchmark different CBOM-Tools on a set of random repositories.

    This command first finds a sample of repositories and then runs the
    specified CBOM tools (kits) on each one, tracking successes and failures.
    """
    start_time = time.time()
    failures = []

    click.echo(f"Fetching {sample_size} GitHub repositories in {language} with size > {min_size}KB...")
    repos = find_repos(language=language, min_size=min_size, max_size=max_size, sample_size=sample_size)
    if not repos:
        click.echo(click.style("No repositories found. Aborting benchmark.", fg='red'))
        return

    click.echo(click.style(f"Starting benchmark on {len(repos)} repositories...", fg='green'))

    # Iterate over each repository and run the specified tools.
    for full_name, clone_url, default_branch, repo_size in repos:
        click.echo(click.style(f"\nRepository: {full_name} (Size: {repo_size}KB)", fg='cyan'))
        for kit in kits:
            click.echo(click.style(f"\nRunning {kit}...", fg='yellow'))

            success = False
            # Match the tool name and call the corresponding test function.
            match kit.lower():
                case "cbomkit":
                    success = test_cbomkit(clone_url, default_branch)
                case "cdxgen":
                    success = test_cdxgen(clone_url, default_branch)
                case "deepseek":
                    success = test_deepseek(clone_url, default_branch)
                case _:
                    click.echo(click.style(f"{kit} is not a valid kit", fg='red'))

            # If the CBOM generation failed, record it.
            if not success:
                failures.append((full_name, kit))

    elapsed = time.time() - start_time
    click.echo(click.style(f"\nFinished Benchmark in {elapsed:.2f}s", fg='blue'))

    # Print a summary of any failures.
    if failures:
        click.echo(click.style("\nCBOM Generation Failures:", fg='red'))
        for repo, kit in failures:
            click.echo(f"- Repository: {repo}, Tool: {kit}")
    else:
        click.echo(click.style("\nAll CBOM generations completed successfully!", fg='green'))


@cli.command()
@click.argument('kits', nargs=-1)
@click.argument('url')
@click.option('--branch', default=None, help='Branch to scan (default: auto-detect).')
def test(kits, url, branch):
    """
    Test one or more CBOM tools on a specific repository URL.

    If the branch is not specified, it will be auto-detected using the GitHub API.
    """
    # Auto-detect the default branch if not provided by the user.
    if branch is None:
        click.echo("No branch specified, retrieving repository information...")
        default_branch = get_repo_info(url)

        if default_branch is None:
            click.echo(click.style("Could not detect repository information. Using 'main' as default branch.", fg='yellow'))
            default_branch = 'main'
        else:
            click.echo(f"Detected default branch: {default_branch}")
    else:
        default_branch = branch
        click.echo(f"Using specified branch: {default_branch}")

    # Run each specified tool on the repository.
    for kit in kits:
        click.echo(click.style(f"\nRunning {kit}...", fg='yellow'))
        match kit.lower():
            case "cbomkit":
                test_cbomkit(url, default_branch)
            case "cdxgen":
                test_cdxgen(url, default_branch)
            case "deepseek":
                test_deepseek(url, default_branch)
            case _:
                click.echo(click.style(f"{kit} is not a valid kit", fg='red'))


def test_cbomkit(url, branch="main"):
    """
    Create a CBOM for a given URL using CBOMkit.

    Args:
        url (str): The URL of the git repository.
        branch (str): The branch to scan. Defaults to "main".

    Returns:
        bool: True if CBOM generation was successful, False otherwise.
    """
    click.echo(f"Trying to create CBOM for {url} with CBOMkit...")
    cbom, duration = cbomkit.generate_cbom(url, branch)
    if cbom:
        click.echo(click.style(f"CBOM retrieved successfully, duration: {duration:.2f} seconds.", fg='green'))
        save_cbom(cbom, url, "cbomkit", duration)
        return True
    else:
        click.echo(click.style("CBOM generation failed.", fg='red'))
        return False


def test_cdxgen(url, branch="main"):
    """
    Create a CBOM for a given URL using cdxgen.

    Args:
        url (str): The URL of the git repository.
        branch (str): The branch to scan. Defaults to "main".

    Returns:
        bool: True if CBOM generation was successful, False otherwise.
    """
    click.echo(f"Trying to create CBOM for {url} with cdxgen...")
    cbom, duration = generate_cdx_cbom(url, branch)
    if cbom:
        click.echo(click.style(f"CBOM retrieved successfully, duration: {duration:.2f} seconds.", fg='green'))
        save_cbom(cbom, url, "cdxgen", duration)
        return True
    else:
        click.echo(click.style("CBOM generation failed.", fg='red'))
        return False


def test_deepseek(url, branch="main"):
    """
    Create a CBOM for a given URL using the DeepSeek API.

    Args:
        url (str): The URL of the git repository.
        branch (str): The branch to scan. Defaults to "main".

    Returns:
        bool: True if CBOM generation was successful, False otherwise.
    """
    click.echo(f"Trying to create CBOM for {url} with deepseek...")
    cbom, duration = deepseek.generate_cbom(url, branch)
    if cbom:
        click.echo(click.style(f"CBOM retrieved successfully, duration: {duration:.2f} seconds.", fg='green'))
        save_cbom(cbom, url, "deepseek", duration)
        return True
    else:
        click.echo(click.style("CBOM generation failed.", fg='red'))
        return False


@cli.command()
@click.option('--save', is_flag=True, help='Save the analysis results to a timestamped CSV file.')
def analyze(save):
    """
    Analyze all generated CBOMs and create a comparison report.

    This command reads all stored CBOM JSON files, calculates statistics,
    and prints summary tables and generates visualizations.
    """
    click.echo(click.style("Starting CBOM analysis...", fg='green'))
    df, stats, timestamp = analyzer.generate_comparison_report(save_csv=save)

    click.echo(click.style(f"\nAnalysis complete! Results and visualizations saved to {analyzer.timestamp_dir}/", fg='green'))
    click.echo(f"Directory: {timestamp}/")

    # Display summary statistics in the console.
    click.echo("\n" + "=" * 50)
    click.echo("SUMMARY STATISTICS")
    click.echo("=" * 50)

    for tool, tool_stats in stats.items():
        click.echo(f"\n{click.style(tool.upper(), fg='cyan')}:")
        click.echo(f"  Total repositories: {tool_stats['total_repos']}")
        click.echo(f"  Empty CBOMs: {tool_stats['empty_cboms']} ({tool_stats['empty_percentage']:.1f}%)")
        click.echo(f"  Average components (non-empty): {tool_stats['avg_components_non_empty']:.1f}")
        # Ensure avg_execution_time is not None before formatting
        avg_time_str = f"{tool_stats.get('avg_execution_time', 0):.2f}s" if tool_stats.get('avg_execution_time') is not None else "N/A"
        click.echo(f"  Average execution time: {avg_time_str}")


@cli.command()
@click.argument('filename', required=False)
def load_analysis(filename):
    """
    Load and visualize a previously saved analysis from a CSV file.

    If no filename is provided, it lists available reports and prompts
    the user to choose one.
    """
    csv_files = analyzer.list_reports()
    if not csv_files:
        click.echo(click.style("No saved analysis reports found.", fg='red'))
        return

    # If no filename is given, prompt the user to select from a list.
    if not filename:
        click.echo("\nEnter the number of the report to load (or the filename):")
        choice = click.prompt("Choice", type=str)
        try:
            # User selected a number from the list.
            index = int(choice) - 1
            if 0 <= index < len(csv_files):
                filename = csv_files[index]
            else:
                click.echo(click.style("Invalid selection", fg='red'))
                return
        except ValueError:
            # User entered a filename directly.
            filename = choice

    click.echo(f"\nLoading analysis from {filename}...")
    df = analyzer.load_and_visualize_csv(filename)

    if df is not None:
        click.echo(click.style(f"\nAnalysis loaded and new visualizations created!", fg='green'))
        click.echo(f"Check {analyzer.timestamp_dir}/ for the generated files.")
    else:
        click.echo(click.style(f"Failed to load or process {filename}", fg='red'))


if __name__ == '__main__':
    cli()