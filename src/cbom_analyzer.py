#!/usr/bin/env python3
"""
CBOM Tool Comparison Analyzer
Compares cryptographic detection capabilities and performance across CBOM tools.
"""

import os
import sys
import json
from collections import Counter, defaultdict
from datetime import datetime

import pandas as pd
import numpy as np
import matplotlib

matplotlib.use('Agg')  # Use a non-interactive backend for saving figures
import matplotlib.pyplot as plt
import seaborn as sns
from tabulate import tabulate

from adapter.github_endpoint import get_repo_sizes

# ---- Constants ----
DEFAULT_CBOM_DIR = "CBOMdata"
DEFAULT_METRICS_DIR = os.path.join(DEFAULT_CBOM_DIR, "metrics")
DEFAULT_REPORTS_DIR = "Reports"
TOOL_NAMES = ["cbomkit", "cdxgen", "deepseek"]


class CBOMComparisonAnalyzer:
    """
    Analyzes and compares results from different CBOM generation tools.

    This class handles loading CBOM files, parsing them, calculating statistics,
    generating comparative tables and visualizations, and exporting results.
    """

    def __init__(self, cbom_dir = DEFAULT_CBOM_DIR, metrics_dir = DEFAULT_METRICS_DIR,
                 reports_dir = DEFAULT_REPORTS_DIR):
        """
        Initializes the analyzer with specified data and report directories.

        Args:
            cbom_dir (str): The directory where tool-specific CBOMs are stored.
            metrics_dir (str): The directory containing performance metrics like durations.
            reports_dir (str): The directory where analysis reports will be saved.
        """
        self.cbom_dir = cbom_dir
        self.metrics_dir = metrics_dir
        self.reports_dir = reports_dir
        self.tools = TOOL_NAMES.copy()
        self.comparison_data = defaultdict(lambda: defaultdict(dict))
        self.timestamp_dir = None
        os.makedirs(self.reports_dir, exist_ok=True)

    def _generate_timestamp(self):
        """
        Generates a timestamp string suitable for filenames and directories.

        Returns:
            str: A timestamp in "YYYY-MM-DD-HH-MM" format.
        """
        return datetime.now().strftime("%Y-%m-%d-%H-%M")

    def _create_timestamp_directory(self):
        """
        Creates a new, timestamped directory for storing the current analysis report.

        This helps in keeping analysis runs separate and organized.

        Returns:
            str: The path to the newly created timestamped directory.
        """
        timestamp = self._generate_timestamp()
        self.timestamp_dir = os.path.join(self.reports_dir, timestamp)
        os.makedirs(self.timestamp_dir, exist_ok=True)
        return self.timestamp_dir

    def analyze_all_cboms(self):
        """
        Iterates through all tool directories and analyzes each CBOM file found.

        The results are stored in the `self.comparison_data` dictionary, structured
        by repository name and then by tool name.
        """
        for tool in self.tools:
            tool_dir = os.path.join(self.cbom_dir, tool)
            if not os.path.exists(tool_dir):
                print(f"Warning: Directory {tool_dir} not found for tool '{tool}'.")
                continue

            cbom_files = [f for f in os.listdir(tool_dir) if f.endswith('.json')]
            print(f"\nAnalyzing {len(cbom_files)} CBOMs from {tool}...")

            for cbom_file in cbom_files:
                repo_name = os.path.splitext(cbom_file)[0]
                file_path = os.path.join(tool_dir, cbom_file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        cbom_data = json.load(f)
                    # The core analysis logic for a single file.
                    analysis = self.analyze_single_cbom(cbom_data, tool)
                    self.comparison_data[repo_name][tool] = analysis
                except Exception as e:
                    print(f"Error analyzing {cbom_file}: {e}")
                    # Store error information for reporting.
                    self.comparison_data[repo_name][tool] = {
                        'total_components': 0,
                        'is_empty': True,
                        'component_types': Counter(),
                        'error': str(e)
                    }

    def analyze_single_cbom(self, cbom_data, tool_name):
        """
        Analyzes a single CBOM data structure to extract key metrics.

        This method is designed to handle different CBOM formats produced by various tools,
        such as the standard CycloneDX format and custom formats.

        Args:
            cbom_data: The loaded CBOM JSON data (can be a dict or list).
            tool_name (str): The name of the tool that generated the CBOM.

        Returns:
            A dictionary containing analysis results like component count and types.
        """
        components = []

        # --- Component Extraction Logic ---
        # This part handles the different JSON structures of the CBOMs.
        if tool_name.lower() in {"cdxgen", "deepseek"}:
            if isinstance(cbom_data, dict):
                components = cbom_data.get("components", [])
        else:
            try:
                if isinstance(cbom_data, list) and cbom_data:
                    bom = cbom_data[0].get("bom") if isinstance(cbom_data[0], dict) else None
                    if bom and isinstance(bom, dict):
                        components = bom.get("components", [])
            except Exception:
                # Fallback for cbomkit if parsing its specific format fails.
                if isinstance(cbom_data, dict):
                    components = cbom_data.get("components", [])

        component_types = Counter()
        for comp in components:
            # Determine the component type. For cbomkit, prioritize 'assetType'.
            if tool_name.lower() not in {"cdxgen", "deepseek"} and isinstance(comp, dict):
                crypto_props = comp.get('cryptoProperties', {})
                comp_type = crypto_props.get('assetType', comp.get("type", "unknown"))
            else:
                comp_type = comp.get("type", "unknown") if isinstance(comp, dict) else "unknown"
            component_types[comp_type] += 1

        print(f"  Found {len(components)} components in {tool_name} CBOM for this repo.")

        return {
            'total_components': len(components),
            'is_empty': len(components) == 0,
            'component_types': component_types,
        }

    def _load_execution_times(self):
        """
        Loads execution time metrics from the 'durations.json' file.

        Returns:
            A dictionary with repository IDs as keys and tool-specific metrics as values.
        """
        metrics_path = os.path.join(self.metrics_dir, "durations.json")
        if not os.path.exists(metrics_path):
            print(f"Warning: Metrics file not found at {metrics_path}")
            return {}
        try:
            with open(metrics_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error loading metrics file: {e}")
            return {}

    def _fetch_all_repo_sizes(self, execution_times):
        """
        Fetches repository sizes (total and language-specific) from the GitHub API.

        Args:
            execution_times: A dictionary containing repository metadata, including URLs.

        Returns:
            A dictionary mapping repository names to a tuple of (total_size, java_size).
        """
        print("\nFetching repository sizes from GitHub API...")
        repo_sizes = {}
        processed_urls = set()

        for repo_name, repo_data in execution_times.items():
            # Get the URL from any available tool entry for the repo.
            url = next((tool_data.get('url') for tool_data in repo_data.values() if isinstance(tool_data, dict)), None)

            if url and url not in processed_urls:
                print(f"  Fetching size for {repo_name}...")
                total_size, java_size = get_repo_sizes(url)
                repo_sizes[repo_name] = (total_size, java_size)
                processed_urls.add(url)
        return repo_sizes

        # In CBOMComparisonAnalyzer class within cbom_analyzer.py

    def generate_comparison_report(self, save_csv=True):
        """
        Generates a comprehensive comparison report.

        This is the main orchestration method that performs analysis, gathers metrics,
        and produces the final reports (tables, plots, and CSV).

        Args:
            save_csv: If True, the final data is exported to a CSV file.

        Returns:
            A tuple containing the results DataFrame, the calculated statistics dictionary,
            and the timestamp string for the report directory.
        """
        self.analyze_all_cboms()
        execution_times = self._load_execution_times()
        repo_sizes = self._fetch_all_repo_sizes(execution_times)

        results = []
        # Combine analysis results, execution times, and repo sizes.
        for repo_name, tools_data in self.comparison_data.items():
            total_size, java_size = repo_sizes.get(repo_name, (None, None))
            for tool, data in tools_data.items():
                exec_time = execution_times.get(repo_name, {}).get(tool, {}).get('duration')
                results.append({
                    'Repository': repo_name,
                    'Tool': tool,
                    'Total_Components': data.get('total_components', 0),
                    'Is_Empty': data.get('is_empty', True),
                    'Execution_Time': exec_time,
                    'Component_Types': data.get('component_types', Counter()),
                    'Repository_Size': total_size,
                    'Java_Size': java_size,
                })

        df = pd.DataFrame(results)
        if df.empty:
            print("No data to report. Aborting.")
            # Return three values to match the expected unpacking
            return pd.DataFrame(), {}, None

        stats = self._calculate_statistics(df)
        # This call creates the timestamped directory and returns its path
        timestamp_path = self._create_timestamp_directory()
        # Extract just the directory name (the timestamp)
        timestamp_name = os.path.basename(timestamp_path)

        self._create_visualizations_and_tables(df, stats)

        if save_csv:
            csv_path = self.export_to_csv(df)
            print(f"\nCSV data saved to: {csv_path}")

        # Return all three values
        return df, stats, timestamp_name

    def _calculate_statistics(self, df):
        """
        Calculates summary statistics for each tool based on the analysis data.

        Args:
            df: A pandas DataFrame containing the combined analysis results.

        Returns:
            A dictionary of calculated statistics, keyed by tool name.
        """
        stats = {}
        for tool in self.tools:
            tool_df = df[df['Tool'] == tool]
            if tool_df.empty:
                continue

            non_empty_df = tool_df[~tool_df['Is_Empty']]
            stats[tool] = {
                'total_repos': len(tool_df),
                'empty_cboms': tool_df['Is_Empty'].sum(),
                'non_empty_cboms': len(non_empty_df),
                'empty_percentage': (tool_df['Is_Empty'].sum() / len(tool_df)) * 100 if len(tool_df) > 0 else 0,
                'avg_components': tool_df['Total_Components'].mean(),
                'avg_components_non_empty': non_empty_df['Total_Components'].mean() if not non_empty_df.empty else 0,
                'total_components': tool_df['Total_Components'].sum(),
                'avg_execution_time': tool_df['Execution_Time'].mean(skipna=True),
                'execution_time_std': tool_df['Execution_Time'].std(skipna=True),
            }
            # Aggregate all component types for the tool.
            all_component_types = Counter()
            for comp_types in tool_df['Component_Types']:
                all_component_types.update(comp_types)
            stats[tool]['component_types'] = dict(all_component_types)
        return stats

    # --------------------------------------------------------------------------
    # --- Report and Visualization Generation ---
    # --------------------------------------------------------------------------

    def _create_visualizations_and_tables(self, df, stats):
        """
        Creates and prints all tables and generates all plot files.
        """
        plt.style.use('default')
        sns.set_palette("husl")
        available_tools = [tool for tool in self.tools if tool in stats]

        # --- Print Tables to Console ---
        self._print_summary_table(stats, available_tools)
        self._print_component_type_table(stats, available_tools)
        self._create_repository_detail_table(df, available_tools,
                                             column='Execution_Time',
                                             title='Execution Time by Repository (seconds)',
                                             format_str="{:.2f}")
        self._create_repository_detail_table(df, available_tools,
                                             column='Total_Components',
                                             title='Components by Repository',
                                             format_str="{:.0f}")

        # --- Generate and Save Plots ---
        self._create_components_bar_chart(stats, available_tools)
        self._create_empty_percentage_chart(stats, available_tools)
        self._create_execution_time_boxplot(df, available_tools)
        self._create_component_types_chart(stats, available_tools)
        self._create_size_vs_time_charts(df, available_tools)

        print(f"\nVisualizations saved to: {self.timestamp_dir}/")

    def _print_summary_table(self, stats, available_tools):
        """Prints the main summary table of tool performance."""
        print("\n=== CBOM Tool Comparison Summary ===\n")
        headers = ['Tool', 'Repos', 'Non-Empty', 'Empty', 'Empty %', 'Total Comp.', 'Avg/Repo', 'Avg/Non-Empty',
                   'Avg Time (s)']
        table_data = []
        for tool in available_tools:
            s = stats[tool]
            avg_time = f"{s['avg_execution_time']:.2f}" if pd.notna(s['avg_execution_time']) else "N/A"
            table_data.append([
                tool.capitalize(), s['total_repos'], s['non_empty_cboms'], s['empty_cboms'],
                f"{s['empty_percentage']:.1f}%", s['total_components'], f"{s['avg_components']:.1f}",
                f"{s['avg_components_non_empty']:.1f}", avg_time
            ])
        print(tabulate(table_data, headers=headers, tablefmt='grid'))

    def _print_component_type_table(self, stats, available_tools):
        """Prints the table showing the distribution of component types per tool."""
        print("\n=== Component Type Distribution ===\n")
        all_types = sorted(
            {comp_type for tool in available_tools for comp_type in stats[tool].get('component_types', {})})
        table_data = []
        for comp_type in all_types:
            row = [comp_type] + [stats[tool]['component_types'].get(comp_type, 0) for tool in available_tools]
            table_data.append(row)
        headers = ['Component Type'] + [t.capitalize() for t in available_tools]
        print(tabulate(table_data, headers=headers, tablefmt='grid'))

    def _create_repository_detail_table(self, df, available_tools, column, title, format_str):
        """
        Generic function to create and print a detailed table of repository metrics.
        This is used for both execution time and component counts to avoid code duplication.
        """
        print(f"\n=== {title} ===\n")
        # Pivot the dataframe to have tools as columns and repos as rows
        pivot_df = df.pivot(index='Repository', columns='Tool', values=column)
        pivot_df = pivot_df[available_tools]  # Ensure column order

        # Add repo size columns
        size_df = df[['Repository', 'Repository_Size', 'Java_Size']].drop_duplicates().set_index('Repository')
        merged_df = size_df.join(pivot_df)

        # Calculate row average
        merged_df['Average'] = merged_df[available_tools].mean(axis=1)

        # Format data for tabulate
        table_data = []
        for repo, row_data in merged_df.iterrows():
            row = [
                repo,
                f"{row_data['Repository_Size']:.0f} KB" if pd.notna(row_data['Repository_Size']) else "N/A",
                f"{row_data['Java_Size']:.0f} KB" if pd.notna(row_data['Java_Size']) else "No Java"
            ]
            # Format tool columns and average
            for tool in available_tools + ['Average']:
                value = row_data.get(tool)
                row.append(format_str.format(value) if pd.notna(value) else "N/A")
            table_data.append(row)

        # Add final average row
        avg_row = ["Average", "", ""] + [
            format_str.format(merged_df[tool].mean()) if pd.notna(merged_df[tool].mean()) else "N/A" for tool in
            available_tools] + [""]
        table_data.append(avg_row)

        headers = ['Repository', 'Total Size', 'Java Size'] + [t.capitalize() for t in available_tools] + ['Average']
        print(tabulate(table_data, headers=headers, tablefmt='grid'))

    def _create_components_bar_chart(self, stats, available_tools):
        """Creates and saves a bar chart for average components per non-empty CBOM."""
        plt.figure(figsize=(10, 6))
        avg_components = [stats[tool]['avg_components_non_empty'] for tool in available_tools]
        bars = plt.bar(available_tools, avg_components, color=['#1f77b4', '#ff7f0e', '#2ca02c'])
        plt.title('Average Components per Non-Empty CBOM', fontsize=14, fontweight='bold')
        plt.ylabel('Average Number of Components')
        plt.xlabel('Tool')
        for bar in bars:
            height = bar.get_height()
            plt.text(bar.get_x() + bar.get_width() / 2., height, f'{height:.1f}', ha='center', va='bottom')

        filepath = os.path.join(self.timestamp_dir, 'avg_components.pdf')
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close()

    def _create_empty_percentage_chart(self, stats, available_tools):
        """Creates and saves a bar chart for the percentage of empty CBOMs."""
        plt.figure(figsize=(10, 6))
        empty_percentages = [stats[tool]['empty_percentage'] for tool in available_tools]
        bars = plt.bar(available_tools, empty_percentages, color=['#d62728', '#9467bd', '#8c564b'])
        plt.title('Percentage of Empty CBOMs', fontsize=14, fontweight='bold')
        plt.ylabel('Percentage (%)')
        plt.xlabel('Tool')
        plt.ylim(0, 100)
        for bar in bars:
            height = bar.get_height()
            plt.text(bar.get_x() + bar.get_width() / 2., height, f'{height:.1f}%', ha='center', va='bottom')

        filepath = os.path.join(self.timestamp_dir, 'empty_percentage.pdf')
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close()

    def _create_execution_time_boxplot(self, df, available_tools):
        """Creates and saves a boxplot for execution time distribution."""
        plt.figure(figsize=(10, 6))
        # Filter out tools with no execution time data to avoid errors
        plot_data = [df[df['Tool'] == tool]['Execution_Time'].dropna() for tool in available_tools]
        valid_tools = [tool for i, tool in enumerate(available_tools) if not plot_data[i].empty]
        valid_plot_data = [data for data in plot_data if not data.empty]

        if valid_plot_data:
            bp = plt.boxplot(valid_plot_data, labels=valid_tools, patch_artist=True)
            colors = ['#1f77b4', '#ff7f0e', '#2ca02c']
            for patch, color in zip(bp['boxes'], colors):
                patch.set_facecolor(color)
            plt.title('Execution Time Distribution', fontsize=14, fontweight='bold')
            plt.ylabel('Time (seconds)')
            plt.xlabel('Tool')
        else:
            plt.text(0.5, 0.5, 'No execution time data available', ha='center', va='center')

        filepath = os.path.join(self.timestamp_dir, 'execution_time.pdf')
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close()

    def _create_component_types_chart(self, stats, available_tools):
        """Creates and saves a bar chart for component types distribution."""
        comp_types_df = pd.DataFrame({
            tool: stats[tool].get('component_types', {}) for tool in available_tools
        }).fillna(0).astype(int)

        if not comp_types_df.empty:
            comp_types_df.plot(kind='bar', figsize=(12, 8), width=0.8)
            plt.title('Component Types Distribution', fontsize=14, fontweight='bold')
            plt.ylabel('Number of Components')
            plt.xlabel('Component Type')
            plt.legend(title='Tool')
            plt.xticks(rotation=45, ha='right')
            plt.tight_layout()

            filepath = os.path.join(self.timestamp_dir, 'component_types.pdf')
            plt.savefig(filepath, dpi=300, bbox_inches='tight')
            plt.close()

    def _create_size_vs_time_charts(self, df, available_tools):
        """
        Creates scatter plots of Java code size vs. execution time.

        This version specifically uses the 'Java_Size' column. Repositories
        without Java code (Java_Size is NaN) are excluded from these plots.

        Args:
            df (pd.DataFrame): The main DataFrame with all analysis data.
            available_tools (list[str]): A list of tools with available data.
        """
        # Filter the DataFrame to include only rows with valid Java_Size and Execution_Time
        plot_df = df[df['Java_Size'].notna() & df['Execution_Time'].notna()].copy()

        if plot_df.empty:
            print("\nSkipping size vs. time charts: No data with both Java size and execution time available.")
            return

        # --- Combined plot for all tools ---
        plt.figure(figsize=(12, 8))
        sns.scatterplot(data=plot_df, x='Java_Size', y='Execution_Time', hue='Tool', style='Tool', s=100, alpha=0.8)

        plt.title('Java Code Size vs. Execution Time (All Tools)', fontsize=14, fontweight='bold')
        plt.xlabel('Java Code Size (KB)')
        plt.ylabel('Execution Time (seconds)')
        plt.grid(True, linestyle='--', alpha=0.6)

        # Save the combined plot with a new name
        filepath = os.path.join(self.timestamp_dir, 'size_vs_time_all.pdf')
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close()

        # --- Individual plot for each tool ---
        for tool in available_tools:
            # Filter data for the specific tool
            tool_df = plot_df[plot_df['Tool'] == tool]

            # We need at least 2 data points to create a regression plot
            if len(tool_df) < 2:
                continue

            plt.figure(figsize=(10, 6))
            sns.regplot(data=tool_df, x='Java_Size', y='Execution_Time', ci=None,
                        scatter_kws={'s': 80, 'alpha': 0.7},
                        line_kws={'color': 'red', 'linestyle': '--'})

            plt.title(f'Java Code Size vs. Execution Time ({tool.capitalize()})', fontsize=14, fontweight='bold')
            plt.xlabel('Java Code Size (KB)')
            plt.ylabel('Execution Time (seconds)')
            plt.grid(True, linestyle='--', alpha=0.6)

            # Save the individual plot with a new name
            filepath = os.path.join(self.timestamp_dir, f'size_vs_time_{tool}.pdf')
            plt.savefig(filepath, dpi=300, bbox_inches='tight')
            plt.close()

    def export_to_csv(self, df):
        """
        Exports the comparison results to a CSV file.

        Component types are flattened into separate columns (e.g., 'Type_algorithm').

        Args:
            df: The DataFrame containing the analysis results.

        Returns:
            The path to the saved CSV file.
        """
        filepath = os.path.join(self.timestamp_dir, "cbom_comparison.csv")

        # Flatten the 'Component_Types' Counter into separate columns
        component_types_df = df['Component_Types'].apply(pd.Series).fillna(0).astype(int)
        component_types_df = component_types_df.add_prefix('Type_')

        # Combine with the main dataframe
        export_df = pd.concat([df.drop('Component_Types', axis=1), component_types_df], axis=1)

        export_df.to_csv(filepath, index=False)
        return filepath

    def list_reports(self):
        """
        Finds and lists all available CSV analysis reports.

        It searches for .csv files in the main reports directory and in any
        timestamped subdirectories.

        Returns:
            A sorted list of available report file paths, newest first.
        """
        if not os.path.exists(self.reports_dir):
            print(f"Reports directory '{self.reports_dir}' does not exist.")
            return []

        csv_files = []
        # Find CSVs in timestamped subdirectories (e.g., Reports/2025-06-10-13-40/)
        for item in os.listdir(self.reports_dir):
            item_path = os.path.join(self.reports_dir, item)
            if os.path.isdir(item_path):
                for file in os.listdir(item_path):
                    if file.endswith('.csv'):
                        # Store the relative path (e.g., "2025-06-10-13-40/cbom_comparison.csv")
                        csv_files.append(os.path.join(item, file))

        # Find legacy CSVs in the root reports directory
        for file in os.listdir(self.reports_dir):
            if file.endswith('.csv') and os.path.isfile(os.path.join(self.reports_dir, file)):
                csv_files.append(file)

        if not csv_files:
            print("No CSV reports found.")
            return []

        # Sort reports, newest first, based on the filename/path
        csv_files.sort(reverse=True)

        print("\nAvailable reports:")
        for i, filename in enumerate(csv_files):
            print(f"{i + 1}. {filename}")
        return csv_files

    def load_and_visualize_csv(self, csv_filename):
        """
        Loads a saved CSV report, reconstructs the data, and regenerates visualizations.

        Args:
            csv_filename (str): The path to the CSV file to load.

        Returns:
            A pandas DataFrame with the loaded data, or None on failure.
        """
        # Build the full path to the report file
        filepath = os.path.join(self.reports_dir, csv_filename)
        if not os.path.exists(filepath):
            print(f"Error: File not found at {filepath}")
            return None

        print(f"Loading data from {filepath}...")
        df = pd.read_csv(filepath)
        reconstructed_data = []

        # Reconstruct the 'Component_Types' Counter from the 'Type_*' columns
        for _, row in df.iterrows():
            comp_types = Counter()
            for col in df.columns:
                if col.startswith('Type_'):
                    type_name = col.replace('Type_', '')
                    if pd.notna(row[col]) and row[col] > 0:
                        comp_types[type_name] = int(row[col])

            row_dict = row.to_dict()
            row_dict['Component_Types'] = comp_types
            reconstructed_data.append(row_dict)

        df_reconstructed = pd.DataFrame(reconstructed_data)
        stats = self._calculate_statistics(df_reconstructed)

        # Set the timestamp directory for saving the new plots
        self.timestamp_dir = os.path.dirname(filepath)

        # Regenerate the tables and plots
        self._create_visualizations_and_tables(df_reconstructed, stats)
        return df_reconstructed

def main():
    """Main entry point to run the CBOM comparison analyzer from the command line."""
    analyzer = CBOMComparisonAnalyzer()

    if len(sys.argv) > 1 and sys.argv[1] == 'load':
        # --- Load and Visualize Mode ---
        pass
    else:
        # --- New Analysis Mode ---
        print("Starting CBOM tool comparison analysis...")
        df, stats = analyzer.generate_comparison_report()
        if not stats:
            print("Analysis finished, but no results were generated.")
            return

        print(f"\nAnalysis complete! Report saved to {analyzer.timestamp_dir}/")
        print("Generated files:")
        print("- cbom_comparison.csv")
        # List PDF files
        for item in os.listdir(analyzer.timestamp_dir):
            if item.endswith(".pdf"):
                print(f"- {item}")

        print("\nTo visualize this report later, use:")
        print(f"  python {sys.argv[0]} load {os.path.join(analyzer.timestamp_dir, 'cbom_comparison.csv')}")


if __name__ == "__main__":
    main()