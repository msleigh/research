#!/usr/bin/env python3
"""Benchmark markdown libraries and generate charts."""
from __future__ import annotations

import csv
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import matplotlib.pyplot as plt

import cmarkgfm
import commonmark
import markdown
import markdown2
import mistune


@dataclass(frozen=True)
class BenchmarkResult:
    library: str
    size_label: str
    size_bytes: int
    iterations: int
    mean_ms: float
    p95_ms: float
    throughput_mb_s: float


SAMPLE_SECTION = """# Sample Document

A paragraph with **bold**, *italic*, ~~strikethrough~~, and `inline code`.

> Blockquote with a [link](https://example.com) and an inline image: ![alt](https://example.com/image.png)

- [x] Task one
- [ ] Task two
- [ ] Task three

1. Ordered item
2. Ordered item
3. Ordered item

| Column A | Column B | Column C |
| --- | --- | --- |
| 1 | 2 | 3 |
| 4 | 5 | 6 |
| 7 | 8 | 9 |

```python
from dataclasses import dataclass

@dataclass
class Example:
    name: str
    value: int

    def render(self) -> str:
        return f"{self.name}: {self.value}"
```

Footnote example.[^1]

[^1]: This is the footnote text.

---

"""


def build_document(repetitions: int) -> str:
    return SAMPLE_SECTION * repetitions


def prepare_renderers() -> dict[str, Callable[[str], str]]:
    markdown_extensions = [
        "fenced_code",
        "tables",
        "footnotes",
        "sane_lists",
        "smarty",
        "toc",
    ]
    markdown2_extras = [
        "fenced-code-blocks",
        "tables",
        "footnotes",
        "strike",
        "smarty-pants",
        "toc",
    ]

    mistune_md = mistune.create_markdown(
        plugins=["strikethrough", "table", "task_lists", "footnotes"]
    )

    return {
        "cmarkgfm": lambda text: cmarkgfm.github_flavored_markdown_to_html(text),
        "markdown": lambda text: markdown.markdown(text, extensions=markdown_extensions),
        "markdown2": lambda text: markdown2.markdown(text, extras=markdown2_extras),
        "mistune": lambda text: mistune_md(text),
        "commonmark": lambda text: commonmark.commonmark(text),
    }


def percentile(values: list[float], percent: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = int(round((len(sorted_values) - 1) * percent))
    return sorted_values[index]


def benchmark_library(
    render: Callable[[str], str],
    document: str,
    iterations: int,
    warmup: int,
) -> tuple[float, float]:
    for _ in range(warmup):
        render(document)

    timings: list[float] = []
    for _ in range(iterations):
        start = time.perf_counter()
        render(document)
        end = time.perf_counter()
        timings.append((end - start) * 1000)

    mean_ms = statistics.mean(timings)
    p95_ms = percentile(timings, 0.95)
    return mean_ms, p95_ms


def run_benchmarks(
    sizes: dict[str, int],
    iterations: int,
    warmup: int,
) -> list[BenchmarkResult]:
    renderers = prepare_renderers()
    results: list[BenchmarkResult] = []

    for size_label, repetitions in sizes.items():
        document = build_document(repetitions)
        size_bytes = len(document.encode("utf-8"))
        for name, render in renderers.items():
            mean_ms, p95_ms = benchmark_library(render, document, iterations, warmup)
            throughput = (size_bytes / 1_000_000) / (mean_ms / 1000)
            results.append(
                BenchmarkResult(
                    library=name,
                    size_label=size_label,
                    size_bytes=size_bytes,
                    iterations=iterations,
                    mean_ms=mean_ms,
                    p95_ms=p95_ms,
                    throughput_mb_s=throughput,
                )
            )
            print(
                f"{name} | {size_label}: {mean_ms:.2f} ms mean, {p95_ms:.2f} ms p95, "
                f"{throughput:.2f} MB/s"
            )

    return results


def write_results_csv(results: Iterable[BenchmarkResult], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "library",
                "size_label",
                "size_bytes",
                "iterations",
                "mean_ms",
                "p95_ms",
                "throughput_mb_s",
            ]
        )
        for result in results:
            writer.writerow(
                [
                    result.library,
                    result.size_label,
                    result.size_bytes,
                    result.iterations,
                    f"{result.mean_ms:.4f}",
                    f"{result.p95_ms:.4f}",
                    f"{result.throughput_mb_s:.4f}",
                ]
            )


def plot_metric(
    results: list[BenchmarkResult],
    metric: str,
    ylabel: str,
    output_path: Path,
) -> None:
    size_labels = sorted({result.size_label for result in results})
    libraries = sorted({result.library for result in results})

    metric_map = {
        "mean_ms": lambda r: r.mean_ms,
        "p95_ms": lambda r: r.p95_ms,
        "throughput_mb_s": lambda r: r.throughput_mb_s,
    }
    metric_func = metric_map[metric]

    fig, ax = plt.subplots(figsize=(10, 6))

    bar_width = 0.15
    x_positions = range(len(size_labels))

    for index, library in enumerate(libraries):
        values = [
            metric_func(result)
            for result in results
            if result.library == library
        ]
        positions = [x + (index - len(libraries) / 2) * bar_width for x in x_positions]
        ax.bar(positions, values, width=bar_width, label=library)

    ax.set_xticks(list(x_positions))
    ax.set_xticklabels(size_labels)
    ax.set_ylabel(ylabel)
    ax.set_title(f"Markdown benchmark: {ylabel} by size")
    ax.legend()
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def main() -> None:
    sizes = {
        "small": 2,
        "medium": 20,
        "large": 120,
    }
    iterations = 20
    warmup = 3

    results = run_benchmarks(sizes, iterations, warmup)

    results_csv = Path(__file__).parent / "data" / "benchmark_results.csv"
    write_results_csv(results, results_csv)

    plot_metric(
        results,
        metric="throughput_mb_s",
        ylabel="Throughput (MB/s)",
        output_path=Path(__file__).parent / "charts" / "throughput.png",
    )
    plot_metric(
        results,
        metric="mean_ms",
        ylabel="Mean render time (ms)",
        output_path=Path(__file__).parent / "charts" / "mean_time.png",
    )


if __name__ == "__main__":
    main()
