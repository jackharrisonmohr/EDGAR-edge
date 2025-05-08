#!/usr/bin/env python3
import argparse

def count_tokens(filename):
    """
    Count the number of whitespace-separated tokens in the given file.
    """
    total = 0
    with open(filename, 'r', encoding='utf-8') as f:
        for line in f:
            # split() with no args splits on any whitespace and drops empty strings
            tokens = line.split()
            total += len(tokens)
    return total

def main():
    parser = argparse.ArgumentParser(
        description="Count the number of whitespace-separated strings in a file."
    )
    parser.add_argument(
        'file',
        help='Path to the input file'
    )
    args = parser.parse_args()
    print(f"Counting tokens in {args.file!r}...")
    count = count_tokens(args.file)
    print(f"Total tokens in {args.file!r}: {count}")

if __name__ == "__main__":
    main()
