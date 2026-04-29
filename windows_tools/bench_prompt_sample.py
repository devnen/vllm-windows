"""Sample long-prompt source for bench_summarize.py.

The skill's headline numbers came from feeding a ~24 k-token Python service
file to the summarisation prompt. To reproduce them you need a comparably
sized, dense Python source. Three options:

1. **Use this file with --code** — but it's a placeholder; the numbers
   will be small.

2. **Use CPython's Lib/inspect.py** (PSF-licensed, compatible). Roughly
   8–10 k tokens. Works fine for relative comparisons but not directly
   comparable to the 24 k headline:
   ```
   python windows_tools\\bench_summarize.py --label test \\
       --code .venv\\Lib\\inspect.py
   ```

3. **Use any of your own ~100 KB Python source files.** Any production
   service module, web framework, or compiler in Python will work. The
   shape that the bench measures is "prefill on a long, dense, in-domain
   prompt + decode 200 tokens of structured summary". The exact file
   doesn't matter as long as you keep using the same one across runs.

The point of the bench is **relative**: do `mem_util=0.948` and
`mem_util=0.92` produce different decode tok/s? Does MTP n=6 beat n=3 on
your prompt class? Cross-machine absolute comparisons are noisy because
of CPU, disk, and driver-version differences.

For absolute headline-style numbers, run the same bench from one of the
example threads in `docs/REDDIT_LAUNCH_RESEARCH.md` and use their prompt.
"""

# Below is a chunk of placeholder content so this file is a valid Python
# module and bench_summarize doesn't crash on import. Replace with your
# own source for real benches.

class Placeholder:
    """A trivial placeholder.

    bench_summarize will summarise this file in 8 bullets — useful for a
    smoke test that the bench harness is wired up correctly, but the
    decode numbers will be artificially fast because the prompt is short.
    """

    def __init__(self, name: str = "placeholder"):
        self.name = name

    def describe(self) -> str:
        return f"This is a placeholder named {self.name}."


def main() -> None:
    p = Placeholder()
    print(p.describe())


if __name__ == "__main__":
    main()
